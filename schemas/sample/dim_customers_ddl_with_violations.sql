CREATE TABLE warehouse.dim_customers (
    customer_sk     BIGINT          NOT NULL,
    customer_id     BIGINT          NOT NULL,
    full_name       VARCHAR(255),
    email           VARCHAR(255),
    country_code    VARCHAR(2)      NOT NULL,
    customer_segment VARCHAR(50),
    is_active       BOOLEAN         NOT NULL,
    valid_from      TIMESTAMPTZ     NOT NULL,
    valid_to        TIMESTAMPTZ,
    is_current      BOOLEAN         NOT NULL
);
