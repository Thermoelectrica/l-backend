# IESK: схема взаимодействия l-mobile → l-backend

Дополнение к [backend-plan.md](backend-plan.md) и [mobile-implementation.md](mobile-implementation.md). Все схемы — mermaid.

## 1. Модель данных

```mermaid
erDiagram
    PLANT ||--o| IESK_PLANT : "признак (1:1, FK)"
    PLANT ||--o{ FACILITY : ""
    FACILITY ||--o{ EQUIPMENT : ""
    EQUIPMENT ||..o{ IESK_INSPECTION : "equipment_id (без FK)"
    INSPECTOR ||--o{ IESK_INSPECTION : "inspector_id (FK)"
    IESK_INSPECTION ||--o{ IESK_IMAGE : "iesk_inspection_id (FK)"
    IMAGE ||..o{ IESK_IMAGE : "image_id (без FK)"
    PLANT ||..o{ IMAGE : "plant_id (без FK)"

    IESK_PLANT {
        uuid plant_id PK
        timestamptz created_at
    }
    IESK_INSPECTION {
        uuid id PK
        uuid equipment_id
        int inspector_id FK
        timestamptz started_at
        timestamptz completed_at
        inspection_status status "PLANNED / IN_PROGRESS / COMPLETED"
        int oil_level
        int bugs
        int dimensions
        int locks
        int stickers
        text comment
        bool is_deleted
        timestamptz server_modified_at
    }
    IESK_IMAGE {
        uuid iesk_inspection_id PK
        uuid image_id PK
        bool is_deleted
    }
```

Агрегаты: **Plant** (+`iesk_plant`), **IeskInspection** (корень + `iesk_image`), **Image** (без изменений, файл в S3).

## 2. Как mobile узнаёт тип станции

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Админ (SQL)
    participant DB as PostgreSQL
    participant API as l-backend
    participant M as l-mobile

    Admin->>DB: mark_iesk_plant.sql: INSERT iesk_plant + UPDATE plant.server_modified_at (один запрос, без триггеров)

    Note over M: обновление списка станций (PlantMetadataRepository), всегда полный список
    M->>API: GET /plant/all
    API->>DB: plant LEFT JOIN iesk_plant
    API-->>M: items[]: {..., external_plant_type: "iesk"}
    M->>M: plant_metadata.external_plant_type = "iesk" (источник истины для UI)

    Note over M: синхронизация станции (PlantSynchronizer)
    M->>API: GET /plant/by_id/{id}
    API-->>M: Plant {..., server_modified_at: новый, external_plant_type: "iesk"}
    M->>M: метка изменилась → локальная plant перезаписана
```

Основной канал — шаг 3–5: mobile запрашивает `/plant/all` целиком (`modifiedSince = null`) и перезаписывает поля `plant_metadata` без сравнения меток, поэтому признак доходит, даже если станцию разметили простым `INSERT` без сдвига метки. Сдвиг метки в скрипте разметки нужен только для того, чтобы шаг 9 обновил и локальную копию `plant`.

## 3. Полный цикл синхронизации станции

`BidirectionalPlantSyncCoordinator.syncPlant`: стадии выполняются последовательно, каждая через `BidirSyncAlgorithm` (pull → push при `SKIP`/`THEIRS`, push(force) → pull при `OURS`).

```mermaid
flowchart TD
    S([syncPlant]) --> P1[1. Plant<br/>GET /plant/by_id]
    P1 --> P2[2. Equipment<br/>/equipment/by_plant_id + PUT]
    P2 --> P3[3. Image метаданные<br/>/image/by_plant_id + PUT /image]
    P3 --> P4[4. Inspection<br/>/inspection/by_plant_id + PUT]
    P4 --> IESK{external_plant_type<br/>== iesk?}
    IESK -- да --> P4b[4b. IeskInspection<br/>/iesk-inspection/by_plant_id + PUT]
    IESK -- нет --> P5
    P4b --> P5[5. Defect]
    P5 --> P6[6. WorkLog]
    P6 --> P7[7. StickerInstallation]
    P7 --> P8[8. EntityProperty]
    P8 --> E([completeSync])
    P3 -. файлы отдельно .-> W[[ImageSyncWorker / PlantImageSyncWorker<br/>S3 presigned upload/download]]
```

Новая стадия идёт **после Image** (связки ссылаются на уже известные картинки) и **после Equipment** (локальный фильтр по станции идёт через `equipment → facility`).

## 4. Создание IESK-осмотра офлайн и отправка на сервер

```mermaid
sequenceDiagram
    autonumber
    actor U as Инспектор
    participant UI as l-mobile UI
    participant L as Room (локальная БД)
    participant SYNC as IeskInspectionSynchronizer
    participant API as l-backend
    participant S3 as Object Storage

    U->>UI: открыть оборудование на IESK-станции
    UI->>L: plant_metadata.external_plant_type == "iesk"
    UI->>U: экран IESK-осмотра вместо мастера шагов
    U->>UI: заполнить чек-лист и комментарий
    UI->>L: iesk_inspection(id=UUID, status=IN_PROGRESS, server_modified_at=NULL, is_dirty=1)
    U->>UI: сделать фото
    UI->>L: image(id, plant_id, sync_status=PENDING_UPLOAD, is_dirty=1) + файл
    UI->>L: iesk_image_link(iesk_inspection_id, image_id), iesk_inspection.is_dirty=1
    U->>UI: завершить осмотр
    UI->>L: status=COMPLETED, completed_at=now, is_dirty=1

    Note over SYNC,API: сеть появилась → syncPlant
    SYNC->>API: стадия 3: PUT /image {id, plant_id, ...}
    API-->>SYNC: 200 Image + presigned upload URL
    SYNC->>API: стадия 4b pull: GET /iesk-inspection/by_plant_id/{plant}?modified_since=max(local)
    API-->>SYNC: [] (нового осмотра на сервере ещё нет)
    SYNC->>API: стадия 4b push: PUT /iesk-inspection?force=false {..., server_modified_at: started_at, image_links:[{image_id}]}
    API->>API: INSPECT, доступ к станции (тип станции не проверяется)
    API-->>SYNC: 200 IeskInspection {server_modified_at: T1}
    SYNC->>L: сохранить ответ, is_dirty=0

    Note over SYNC,S3: ImageSyncWorker (независимо)
    SYNC->>S3: PUT файл по presigned URL
    S3-->>API: callback ObjectCreate → image.upload_status=UPLOADED
```

## 5. Изменение и удаление (оптимистичная блокировка)

```mermaid
sequenceDiagram
    autonumber
    participant A as Устройство A
    participant B as Устройство B
    participant API as l-backend

    Note over A,B: оба имеют осмотр X с server_modified_at = T1
    A->>API: PUT /iesk-inspection {id:X, server_modified_at:T1, comment:"a"}
    API-->>A: 200 {server_modified_at:T2}
    B->>API: PUT /iesk-inspection {id:X, server_modified_at:T1, comment:"b"}
    API-->>B: 409 ConflictError {server_modified_at:T2, client_modified_at:T1}
    alt стратегия SKIP (по умолчанию)
        B->>B: is_in_conflict=1, конфликт в plant_metadata → UI
    else THEIRS
        B->>API: GET /iesk-inspection/by_id/X
        API-->>B: версия T2 → перезаписать локальную
    else OURS
        B->>API: PUT /iesk-inspection?force=true
        API-->>B: 200 {server_modified_at:T3}
    end
```

- **Удаление осмотра**: локально `is_deleted=1, is_dirty=1` → PUT с `is_deleted=true`. Другие устройства получают надгробие через `by_plant_id?modified_since`.
- **Удаление фото из осмотра**: локальная связка удаляется, корень становится `is_dirty=1`. PUT без этого `image_id` → сервер ставит связке `is_deleted=true`. При pull mobile отбрасывает связки с `is_deleted=true`.
- **Потерянный ответ** (сервер записал, клиент не получил): повтор PUT → 409. При pull `areEntitiesEqual` сравнивает поля и связки: если всё совпало, ложный конфликт снимается автоматически (`Sync-Principles.md`, раздел про потерянный ответ).

## 6. Контракт API (кратко)

| Метод и путь | Тело / параметры | Ответ | Ошибки |
|---|---|---|---|
| `GET /plant/all` | `modified_since` | `{items:[{..., external_plant_type: "iesk"\|null}]}` | — |
| `GET /plant/by_id/{id}` | — | `Plant {..., external_plant_type}` | 403, 404 |
| `GET /iesk-inspection/by_plant_id/{plant_id}` | `modified_since` | `IeskInspection[]` | 403 |
| `GET /iesk-inspection/by_id/{id}` | — | `IeskInspection` | 403, 404 |
| `GET /iesk-inspection/all` | `modified_since` | `{items: IeskInspectionListItem[]}` | — |
| `PUT /iesk-inspection` | `IeskInspection`, `force` | `IeskInspection` | 400 (нет оборудования / FK), 403, 409, 422 |
| `PUT /image`, `GET /image/...` | без изменений | | |
| `/inspection/*` | без изменений, работает и на IESK-станциях | | |

Пример `IeskInspection`:
```json
{
  "id": "0b6f…",
  "equipment_id": "9a1c…",
  "inspector_id": 7,
  "started_at": "2026-11-19T08:30:00Z",
  "completed_at": "2026-11-19T08:42:00Z",
  "status": "COMPLETED",
  "oil_level": 1,
  "bugs": 0,
  "dimensions": 2,
  "locks": 1,
  "stickers": 3,
  "comment": "Течь масла не обнаружена",
  "is_deleted": false,
  "server_modified_at": "2026-11-19T08:31:12.345Z",
  "image_links": [{"image_id": "c3d2…", "is_deleted": false}]
}
```
