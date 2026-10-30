-- Recover a rotated refresh token when its response was lost in transit.
-- Nullable for tokens rotated before this migration; never stores plaintext tokens.
ALTER TABLE lesiv.tokens
    ADD COLUMN replacement_token_encrypted TEXT;

COMMENT ON COLUMN lesiv.tokens.replacement_token_encrypted IS
    'RSA-OAEP/SHA-256 encrypted replacement refresh token; recovery is limited by used_at and REUSE_LIFETIME_MIN.';
