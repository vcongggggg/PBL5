from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Cấu hình MySQL cho SQLAlchemy.
# Sửa lại USER, PASSWORD, HOST, PORT, DB_NAME cho phù hợp.
MYSQL_USER = "root"
MYSQL_PASSWORD = "123456789"
MYSQL_HOST = "127.0.0.1"
MYSQL_PORT = 3306
MYSQL_DB = "pbl5"

SQLALCHEMY_DATABASE_URL = (
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
)

engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
  db = SessionLocal()
  try:
      yield db
  finally:
      db.close()

