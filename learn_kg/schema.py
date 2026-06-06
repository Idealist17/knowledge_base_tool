from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "project"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending")


class ProjectPlatform(Base):
    __tablename__ = "project_platform"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), unique=True)
    platform_id: Mapped[str] = mapped_column(String(128), index=True, unique=True)


class Category(Base):
    __tablename__ = "category"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)


class ProjectCategory(Base):
    __tablename__ = "project_category"
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("category.id"), primary_key=True)


class SemanticNode(Base):
    __tablename__ = "semantic_node"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    definition: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(64))


class SemanticFunction(Base):
    __tablename__ = "semantic_function"
    id: Mapped[int] = mapped_column(primary_key=True)
    semantic_node_id: Mapped[int] = mapped_column(ForeignKey("semantic_node.id", ondelete="CASCADE"), index=True)
    function_name: Mapped[str] = mapped_column(String(512))
    contract_path: Mapped[str] = mapped_column(String(1024))


class SemanticMerge(Base):
    __tablename__ = "semantic_merge"
    from_semantic_id: Mapped[int] = mapped_column(ForeignKey("semantic_node.id", ondelete="CASCADE"), primary_key=True)
    to_semantic_id: Mapped[int] = mapped_column(ForeignKey("semantic_node.id", ondelete="CASCADE"), primary_key=True)


class ProjectSemantic(Base):
    __tablename__ = "project_semantic"
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), primary_key=True)
    semantic_node_id: Mapped[int] = mapped_column(ForeignKey("semantic_node.id", ondelete="CASCADE"), primary_key=True)


class AuditFinding(Base):
    __tablename__ = "audit_finding"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(32))
    root_cause: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    patterns: Mapped[str] = mapped_column(Text)
    exploits: Mapped[str] = mapped_column(Text)


class FindingCategory(Base):
    __tablename__ = "finding_category"
    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(512))
    description: Mapped[str] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("category", "name"),)


class AuditFindingCategory(Base):
    __tablename__ = "audit_finding_category"
    audit_finding_id: Mapped[int] = mapped_column(ForeignKey("audit_finding.id", ondelete="CASCADE"), primary_key=True)
    finding_category_id: Mapped[int] = mapped_column(ForeignKey("finding_category.id"), primary_key=True)


class FindingMerge(Base):
    __tablename__ = "finding_merge"
    from_finding_id: Mapped[int] = mapped_column(ForeignKey("audit_finding.id", ondelete="CASCADE"), primary_key=True)
    to_finding_id: Mapped[int] = mapped_column(ForeignKey("audit_finding.id", ondelete="CASCADE"), primary_key=True)


class ProjectFinding(Base):
    __tablename__ = "project_finding"
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), primary_key=True)
    audit_finding_id: Mapped[int] = mapped_column(ForeignKey("audit_finding.id", ondelete="CASCADE"), primary_key=True)


class SemanticFindingLink(Base):
    __tablename__ = "semantic_finding_link"
    semantic_node_id: Mapped[int] = mapped_column(ForeignKey("semantic_node.id", ondelete="CASCADE"), primary_key=True)
    audit_finding_id: Mapped[int] = mapped_column(ForeignKey("audit_finding.id", ondelete="CASCADE"), primary_key=True)
    strength: Mapped[str] = mapped_column(String(16), index=True)
    evidence: Mapped[str] = mapped_column(Text)


class FindingLinkStatus(Base):
    __tablename__ = "finding_link_status"
    audit_finding_id: Mapped[int] = mapped_column(ForeignKey("audit_finding.id", ondelete="CASCADE"), primary_key=True)


class PendingSemantic(Base):
    __tablename__ = "pending_semantic"
    semantic_node_id: Mapped[int] = mapped_column(ForeignKey("semantic_node.id", ondelete="CASCADE"), primary_key=True)
