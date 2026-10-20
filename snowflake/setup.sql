-- Run once in a Snowflake worksheet as ACCOUNTADMIN, after replacing PUBLIC_KEY_HERE with the
-- contents of your public key (the base64 between the BEGIN and END lines, on one line).
-- The warehouse is the smallest size and suspends after 60 seconds, so it only uses credits
-- while the pipeline is running.

create warehouse if not exists kiloplan_wh
    warehouse_size = 'XSMALL' auto_suspend = 60 auto_resume = true initially_suspended = true;

create database if not exists kiloplan;
create schema if not exists kiloplan.raw;

create role if not exists kiloplan_pipeline;
grant usage, operate on warehouse kiloplan_wh to role kiloplan_pipeline;
grant all on database kiloplan to role kiloplan_pipeline;
grant all on all schemas in database kiloplan to role kiloplan_pipeline;
grant create schema on database kiloplan to role kiloplan_pipeline;

create user if not exists kiloplan_pipeline
    default_role = kiloplan_pipeline
    default_warehouse = kiloplan_wh
    rsa_public_key = 'PUBLIC_KEY_HERE';
grant role kiloplan_pipeline to user kiloplan_pipeline;
