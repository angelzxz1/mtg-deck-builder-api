from sqlalchemy import create_engine, Column, Integer, String, Float, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# URL de la base de datos (SQLite local)
SQLALCHEMY_DATABASE_URL = os.getenv("DB_PATH", "sqlite:///./decks.db")

# Crear el motor
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# Sesión local para interactuar con la DB
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base para los modelos
Base = declarative_base()

# --- MODELO DE LA TABLA 'DECKS' ---


class DeckModel(Base):
    __tablename__ = "decks"

    id = Column(Integer, primary_key=True, index=True)
    commander = Column(String, index=True)
    archetype = Column(String)
    budget = Column(Float)
    currency = Column(String)

    # Guardamos listas complejas como JSON (texto)
    deck_list = Column(JSON)      # La lista de cartas
    analytics = Column(JSON)      # Curva de maná, colores, etc.
    export_text = Column(Text)    # Texto para Moxfield
    excel_base64 = Column(Text)   # El archivo Excel codificado


# Crear las tablas automáticamente al importar
Base.metadata.create_all(bind=engine)

# Dependencia para obtener la DB en los endpoints


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
