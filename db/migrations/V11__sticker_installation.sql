CREATE TYPE lesiv.sticker_event_kind AS ENUM ('INSTALLATION', 'REPLACEMENT', 'ADJUSTMENT');
 -- INSTALLATION - монтаж новых наклеек
 -- REPLACEMENT - замена поврежденных или сработавших
 -- ADJUSTMENT - коррекция количества, реально ничего не устанавливалось

CREATE TYPE lesiv.sticker_color AS ENUM ('YELLOW', 'RED', 'GREEN', 'BLUE', 'REFLECTIVE');
-- Цветов только пять: 3 фазы, нейтраль и универсальная

CREATE TABLE lesiv.sticker_installation (
    id UUID PRIMARY KEY,                        -- суррогатный ключ                      
    control_point_id UUID NOT NULL,             -- на какую контрольную точку ставим
    inspector_id INT NOT NULL,                  -- кто ставил
    kind lesiv.sticker_event_kind NOT NULL,     -- INSTALLATION | REPLACEMENT | ADJUSTMENT
    sticker_type_id INT NOT NULL,               -- какой тип ТИН был установлен
    sticker_color lesiv.sticker_color NOT NULL, -- Цвет ТИН
    from_sticker_type_id INT,                   -- Только для замены, тип наклейки который был до того
    count INT NOT NULL,                         -- количество штук
    installed_at TIMESTAMPTZ NOT NULL,          -- время установки
    server_modified_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    -- is_deleted нет
);

CREATE INDEX idx_sticker_installation_cp ON lesiv.sticker_installation(control_point_id);