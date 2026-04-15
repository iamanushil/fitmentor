import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    clerk_user_id: Mapped[str] = mapped_column(unique=True, index=True)
    email: Mapped[str | None] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    fitness_profile: Mapped["FitnessProfile | None"] = relationship(
        back_populates="user", uselist=False
    )


class FitnessProfile(Base):
    __tablename__ = "fitness_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )

    # What the user wants to achieve — e.g. ["lose_fat", "build_strength"]
    goals: Mapped[list | None] = mapped_column(JSONB)
    # "beginner" | "intermediate" | "advanced"
    experience: Mapped[str | None]
    # [{body_part, notes}]
    injuries: Mapped[list | None] = mapped_column(JSONB)
    # ["dumbbells", "pullup_bar"]
    equipment: Mapped[list | None] = mapped_column(JSONB)

    days_per_week: Mapped[int | None]
    session_minutes: Mapped[int | None]
    height_cm: Mapped[int | None]
    weight_kg: Mapped[float | None]

    # "pending" | "ready"
    status: Mapped[str] = mapped_column(server_default=text("'pending'"))
    version: Mapped[int] = mapped_column(server_default=text("1"))

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="fitness_profile")
