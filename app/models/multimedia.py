from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class GalleryPhoto(Base):
    __tablename__ = "gallery_photos"
    __table_args__ = (
        CheckConstraint(
            "category IN ('leaders','events','spiritual','inaugurations','sports','others')",
            name="ck_gallery_photos_category",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(50))
    photo_url: Mapped[str] = mapped_column(Text, nullable=False)
    caption: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    date_added: Mapped[date] = mapped_column(Date, server_default=text("CURRENT_DATE"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("staff_users.id"))


class Mp3Song(Base):
    __tablename__ = "mp3_songs"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(255))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    play_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    download_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    date_added: Mapped[date] = mapped_column(Date, server_default=text("CURRENT_DATE"))


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (
        CheckConstraint("video_source IN ('youtube','upload')", name="ck_videos_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    video_source: Mapped[str] = mapped_column(String(20), nullable=False)
    youtube_url: Mapped[str | None] = mapped_column(Text)
    video_file_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    upload_date: Mapped[date] = mapped_column(Date, server_default=text("CURRENT_DATE"))


class PressGalleryItem(Base):
    __tablename__ = "press_gallery"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    photo_url: Mapped[str | None] = mapped_column(Text)
    caption: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    date_added: Mapped[date] = mapped_column(Date, server_default=text("CURRENT_DATE"))
