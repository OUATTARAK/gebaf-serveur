from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Text, Float, Date, DateTime, Boolean,
    ForeignKey, Enum as SAEnum,
)
from sqlalchemy.orm import relationship
import enum

from app.db import Base


# -------- Enums --------

class UserRole(str, enum.Enum):
    ADMIN = "admin"          # tout
    MANAGER = "manager"      # coordinateur : chantiers, devis, factures
    WORKER = "worker"        # ouvrier : voit ses chantiers, saisit heures/photos
    ACCOUNTANT = "accountant"  # compta : factures, paiements, dépenses
    VIEWER = "viewer"        # lecture seule


class ClientType(str, enum.Enum):
    PARTICULIER = "particulier"
    PROFESSIONNEL = "professionnel"
    COLLECTIVITE = "collectivite"


class ContactType(str, enum.Enum):
    FOURNISSEUR = "fournisseur"
    ARTISAN = "artisan"
    SOUS_TRAITANT = "sous_traitant"
    AUTRE = "autre"


class ChantierStatus(str, enum.Enum):
    PROSPECT = "prospect"
    DEVIS = "devis"
    EN_COURS = "en_cours"
    EN_PAUSE = "en_pause"
    TERMINE = "termine"
    ANNULE = "annule"


class DevisStatus(str, enum.Enum):
    BROUILLON = "brouillon"
    ENVOYE = "envoye"
    ACCEPTE = "accepte"
    REFUSE = "refuse"
    EXPIRE = "expire"


class FactureStatus(str, enum.Enum):
    BROUILLON = "brouillon"
    ENVOYEE = "envoyee"
    PARTIELLEMENT_PAYEE = "partiellement_payee"
    PAYEE = "payee"
    EN_RETARD = "en_retard"
    ANNULEE = "annulee"


class DepenseCategory(str, enum.Enum):
    MATERIAUX = "materiaux"
    SOUS_TRAITANCE = "sous_traitance"
    LOCATION = "location"
    TRANSPORT = "transport"
    FOURNITURES = "fournitures"
    MAIN_OEUVRE = "main_oeuvre"
    AUTRE = "autre"


class DocumentType(str, enum.Enum):
    PHOTO_AVANT = "photo_avant"
    PHOTO_APRES = "photo_apres"
    PHOTO_CHANTIER = "photo_chantier"
    PLAN = "plan"
    CONTRAT = "contrat"
    ATTESTATION = "attestation"
    FACTURE_RECUE = "facture_recue"
    AUTRE = "autre"


class InterventionStatus(str, enum.Enum):
    PLANIFIEE = "planifiee"
    EN_COURS = "en_cours"
    TERMINEE = "terminee"
    ANNULEE = "annulee"


# -------- Modèles --------

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(SAEnum(UserRole), nullable=False, default=UserRole.WORKER)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    chantiers = relationship("Chantier", back_populates="created_by_user", foreign_keys="Chantier.created_by")
    heures = relationship("HeuresTravail", back_populates="user")


class Client(Base):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    type = Column(SAEnum(ClientType), default=ClientType.PARTICULIER, nullable=False)
    email = Column(String(255))
    phone = Column(String(50))
    address = Column(Text)
    siret = Column(String(20))
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    chantiers = relationship("Chantier", back_populates="client")


class Contact(Base):
    __tablename__ = "contacts"
    id = Column(Integer, primary_key=True)
    type = Column(SAEnum(ContactType), default=ContactType.FOURNISSEUR, nullable=False)
    name = Column(String(255), nullable=False)
    company = Column(String(255))
    email = Column(String(255))
    phone = Column(String(50))
    address = Column(Text)
    specialty = Column(String(255))
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Chantier(Base):
    __tablename__ = "chantiers"
    id = Column(Integer, primary_key=True)
    reference = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id"))
    address = Column(Text)
    description = Column(Text)
    status = Column(SAEnum(ChantierStatus), default=ChantierStatus.PROSPECT, nullable=False)
    start_date = Column(Date)
    end_date = Column(Date)
    budget_ht = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"))

    client = relationship("Client", back_populates="chantiers")
    created_by_user = relationship("User", back_populates="chantiers", foreign_keys=[created_by])
    devis = relationship("Devis", back_populates="chantier", cascade="all, delete-orphan")
    factures = relationship("Facture", back_populates="chantier", cascade="all, delete-orphan")
    depenses = relationship("Depense", back_populates="chantier", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="chantier", cascade="all, delete-orphan")
    interventions = relationship("Intervention", back_populates="chantier", cascade="all, delete-orphan")
    heures = relationship("HeuresTravail", back_populates="chantier", cascade="all, delete-orphan")
    assignments = relationship("ChantierAssignment", back_populates="chantier", cascade="all, delete-orphan")


class ChantierAssignment(Base):
    __tablename__ = "chantier_assignments"
    id = Column(Integer, primary_key=True)
    chantier_id = Column(Integer, ForeignKey("chantiers.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String(100))  # libre: chef de chantier, ouvrier, suiveur

    chantier = relationship("Chantier", back_populates="assignments")
    user = relationship("User")


class Devis(Base):
    __tablename__ = "devis"
    id = Column(Integer, primary_key=True)
    number = Column(String(50), unique=True, nullable=False, index=True)
    chantier_id = Column(Integer, ForeignKey("chantiers.id"), nullable=False)
    date = Column(Date, default=date.today, nullable=False)
    validity_date = Column(Date)
    total_ht = Column(Float, default=0.0, nullable=False)
    tva_rate = Column(Float, default=20.0, nullable=False)
    total_ttc = Column(Float, default=0.0, nullable=False)
    status = Column(SAEnum(DevisStatus), default=DevisStatus.BROUILLON, nullable=False)
    notes = Column(Text)
    accepted_date = Column(Date)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    chantier = relationship("Chantier", back_populates="devis")
    items = relationship("DevisItem", back_populates="devis", cascade="all, delete-orphan", order_by="DevisItem.ordering")
    facture = relationship("Facture", back_populates="devis", uselist=False)


class DevisItem(Base):
    __tablename__ = "devis_items"
    id = Column(Integer, primary_key=True)
    devis_id = Column(Integer, ForeignKey("devis.id"), nullable=False)
    ordering = Column(Integer, default=0, nullable=False)
    description = Column(Text, nullable=False)
    quantity = Column(Float, default=1.0, nullable=False)
    unit = Column(String(20), default="u")
    unit_price_ht = Column(Float, default=0.0, nullable=False)

    devis = relationship("Devis", back_populates="items")

    @property
    def total_ht(self):
        return round(self.quantity * self.unit_price_ht, 2)


class Facture(Base):
    __tablename__ = "factures"
    id = Column(Integer, primary_key=True)
    number = Column(String(50), unique=True, nullable=False, index=True)
    chantier_id = Column(Integer, ForeignKey("chantiers.id"), nullable=False)
    devis_id = Column(Integer, ForeignKey("devis.id"))
    date = Column(Date, default=date.today, nullable=False)
    due_date = Column(Date)
    total_ht = Column(Float, default=0.0, nullable=False)
    tva_rate = Column(Float, default=20.0, nullable=False)
    total_ttc = Column(Float, default=0.0, nullable=False)
    paid_amount = Column(Float, default=0.0, nullable=False)
    status = Column(SAEnum(FactureStatus), default=FactureStatus.BROUILLON, nullable=False)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    chantier = relationship("Chantier", back_populates="factures")
    devis = relationship("Devis", back_populates="facture")
    items = relationship("FactureItem", back_populates="facture", cascade="all, delete-orphan", order_by="FactureItem.ordering")
    paiements = relationship("Paiement", back_populates="facture", cascade="all, delete-orphan")

    @property
    def reste_a_payer(self):
        return round(self.total_ttc - (self.paid_amount or 0), 2)


class FactureItem(Base):
    __tablename__ = "facture_items"
    id = Column(Integer, primary_key=True)
    facture_id = Column(Integer, ForeignKey("factures.id"), nullable=False)
    ordering = Column(Integer, default=0, nullable=False)
    description = Column(Text, nullable=False)
    quantity = Column(Float, default=1.0, nullable=False)
    unit = Column(String(20), default="u")
    unit_price_ht = Column(Float, default=0.0, nullable=False)

    facture = relationship("Facture", back_populates="items")

    @property
    def total_ht(self):
        return round(self.quantity * self.unit_price_ht, 2)


class Paiement(Base):
    __tablename__ = "paiements"
    id = Column(Integer, primary_key=True)
    facture_id = Column(Integer, ForeignKey("factures.id"), nullable=False)
    date = Column(Date, default=date.today, nullable=False)
    amount = Column(Float, nullable=False)
    method = Column(String(50))  # virement, chèque, espèces, carte
    reference = Column(String(100))
    notes = Column(Text)

    facture = relationship("Facture", back_populates="paiements")


class Depense(Base):
    __tablename__ = "depenses"
    id = Column(Integer, primary_key=True)
    chantier_id = Column(Integer, ForeignKey("chantiers.id"), nullable=False)
    date = Column(Date, default=date.today, nullable=False)
    supplier_id = Column(Integer, ForeignKey("contacts.id"))
    category = Column(SAEnum(DepenseCategory), default=DepenseCategory.MATERIAUX, nullable=False)
    description = Column(Text, nullable=False)
    quantity = Column(Float, default=1.0)
    unit = Column(String(20))
    amount_ht = Column(Float, default=0.0, nullable=False)
    tva_rate = Column(Float, default=20.0, nullable=False)
    amount_ttc = Column(Float, default=0.0, nullable=False)
    receipt_path = Column(String(500))  # justificatif joint
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    chantier = relationship("Chantier", back_populates="depenses")
    supplier = relationship("Contact")


class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    chantier_id = Column(Integer, ForeignKey("chantiers.id"), nullable=False)
    original_name = Column(String(500), nullable=False)
    file_path = Column(String(500), nullable=False)
    mime_type = Column(String(100))
    size_bytes = Column(Integer)
    doc_type = Column(SAEnum(DocumentType), default=DocumentType.AUTRE, nullable=False)
    description = Column(Text)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"))

    chantier = relationship("Chantier", back_populates="documents")
    uploader = relationship("User")


class Intervention(Base):
    __tablename__ = "interventions"
    id = Column(Integer, primary_key=True)
    chantier_id = Column(Integer, ForeignKey("chantiers.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    start_dt = Column(DateTime, nullable=False)
    end_dt = Column(DateTime, nullable=False)
    assignee_id = Column(Integer, ForeignKey("users.id"))
    contact_id = Column(Integer, ForeignKey("contacts.id"))  # ex: artisan externe
    status = Column(SAEnum(InterventionStatus), default=InterventionStatus.PLANIFIEE, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    chantier = relationship("Chantier", back_populates="interventions")
    assignee = relationship("User")
    contact = relationship("Contact")


class HeuresTravail(Base):
    __tablename__ = "heures_travail"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    chantier_id = Column(Integer, ForeignKey("chantiers.id"), nullable=False)
    date = Column(Date, default=date.today, nullable=False)
    hours = Column(Float, nullable=False)
    description = Column(Text)
    hourly_rate = Column(Float, default=0.0)  # facultatif, pour calcul coût main d'œuvre
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="heures")
    chantier = relationship("Chantier", back_populates="heures")


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String(100), nullable=False)
    entity_type = Column(String(100))
    entity_id = Column(Integer)
    details = Column(Text)

    user = relationship("User")


class Setting(Base):
    """Stockage clé/valeur pour les paramètres modifiables depuis l'admin
    (infos société, clé API IA, etc.)."""
    __tablename__ = "settings"
    key = Column(String(100), primary_key=True)
    value = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
