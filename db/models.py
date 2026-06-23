from datetime import datetime
from sqlalchemy import BigInteger, String, Integer, DateTime, ForeignKey, Text, Boolean, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64))
    full_name: Mapped[str] = mapped_column(String(256))
    credits: Mapped[int] = mapped_column(Integer, default=0)
    is_unlimited: Mapped[bool] = mapped_column(Boolean, default=False)
    subscription_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    current_model: Mapped[str] = mapped_column(String(64), default="llama-3.3-70b")
    current_image_model: Mapped[str] = mapped_column(String(64), default="flux-free")
    waiting_for_image: Mapped[bool] = mapped_column(Boolean, default=False)
    current_music_model: Mapped[str] = mapped_column(String(64), default="elevenmusic-free")
    waiting_for_music: Mapped[bool] = mapped_column(Boolean, default=False)
    referred_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    daily_credits_claimed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user")

    @property
    def has_unlimited_access(self) -> bool:
        """True если у пользователя безлимитный доступ (постоянный или по подписке)."""
        if self.is_unlimited:
            return True
        if self.subscription_until and self.subscription_until > datetime.now():
            return True
        return False


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    model_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(Integer, ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String(16))  # "user" или "assistant"
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    charge_id: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default="XTR")
    payload: Mapped[str] = mapped_column(String(256))
    subscription_until: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
