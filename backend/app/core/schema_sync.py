from sqlalchemy import inspect, text


def sync_schema(engine) -> None:
    """Keep old local databases usable by adding new columns when needed."""
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    with engine.begin() as conn:
        if "parking_sessions" in table_names:
            parking_columns = {col["name"] for col in inspector.get_columns("parking_sessions")}
            required_parking_columns = {
                "gate_type": "VARCHAR(10) DEFAULT 'entry'",
                "trigger_type": "VARCHAR(10) DEFAULT 'sensor'",
                "trigger_source_id": "VARCHAR(50) NULL",
                "rfid_tag": "VARCHAR(100) NULL",
                "plate_in": "VARCHAR(20) NULL",
                "plate_out": "VARCHAR(20) NULL",
                "match_status": "VARCHAR(20) DEFAULT 'pending'",
                "confidence_in": "FLOAT NULL",
                "confidence_out": "FLOAT NULL",
                "rfid_card_id": "INT NULL",
                "rfid_card_type": "VARCHAR(20) NULL",
            }
            for col_name, ddl in required_parking_columns.items():
                if col_name in parking_columns:
                    continue
                conn.execute(text(f"ALTER TABLE parking_sessions ADD COLUMN {col_name} {ddl}"))

        if "subscriptions" in table_names:
            sub_columns = {col["name"] for col in inspector.get_columns("subscriptions")}
            required_sub_columns = {
                "monthly_user_id": "INT NULL",
                "registered_at": "DATETIME NULL",
            }
            for col_name, ddl in required_sub_columns.items():
                if col_name in sub_columns:
                    continue
                conn.execute(text(f"ALTER TABLE subscriptions ADD COLUMN {col_name} {ddl}"))

        if "rfid_cards" in table_names:
            rfid_columns = {col["name"] for col in inspector.get_columns("rfid_cards")}
            required_rfid_columns = {
                "status": "VARCHAR(20) DEFAULT 'available'",
            }
            for col_name, ddl in required_rfid_columns.items():
                if col_name in rfid_columns:
                    continue
                conn.execute(text(f"ALTER TABLE rfid_cards ADD COLUMN {col_name} {ddl}"))

        if "pending_scans" in table_names:
            pending_cols = {col["name"] for col in inspector.get_columns("pending_scans")}
            required_pending_cols = {
                "scan_token": "VARCHAR(100) NULL",
            }
            for col_name, ddl in required_pending_cols.items():
                if col_name in pending_cols:
                    continue
                conn.execute(text(f"ALTER TABLE pending_scans ADD COLUMN {col_name} {ddl}"))
