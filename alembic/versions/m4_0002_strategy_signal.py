from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "m4_0002"
down_revision = "m4_0001"
branch_labels = None
depends_on = None


def _id_column() -> sa.Column:
    return sa.Column(
        "id",
        sa.BigInteger(),
        sa.Identity(start=1),
        nullable=False,
    )


def _created_at_column() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "strategy_signal",
        _id_column(),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("strategy_version_id", sa.BigInteger(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("subject_type", sa.String(length=16), nullable=False),
        sa.Column("subject_key", sa.String(length=128), nullable=False),
        sa.Column("instrument_id", sa.BigInteger(), nullable=True),
        sa.Column("signal_role", sa.String(length=32), nullable=False),
        sa.Column("signal_side", sa.String(length=16), nullable=False),
        sa.Column("signal_action", sa.String(length=32), nullable=False),
        sa.Column("raw_score", sa.Numeric(18, 8), nullable=True),
        sa.Column("normalized_score", sa.Numeric(18, 8), nullable=True),
        sa.Column("confidence_score", sa.Numeric(18, 8), nullable=True),
        sa.Column("rank_in_batch", sa.Integer(), nullable=True),
        sa.Column("universe_size", sa.Integer(), nullable=True),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column(
            "reason_payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "parameter_payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        _created_at_column(),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["ops_run.id"],
            name="fk_ss__run_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["strategy_version_id"],
            ["strategy_version.id"],
            name="fk_ss__ver_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["meta_instrument.id"],
            name="fk_ss__instr_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ss"),
        sa.UniqueConstraint(
            "run_id",
            "strategy_version_id",
            "as_of_date",
            "subject_key",
            "signal_action",
            name="uq_ss__run_ver_date_subj_act",
        ),
    )
    op.create_index(
        "ix_ss__ver_date",
        "strategy_signal",
        ["strategy_version_id", "as_of_date"],
        unique=False,
    )
    op.create_index(
        "ix_ss__eff_date",
        "strategy_signal",
        ["effective_date"],
        unique=False,
    )
    op.create_index(
        "ix_ss__instr_eff_date",
        "strategy_signal",
        ["instrument_id", "effective_date"],
        unique=False,
    )
    op.create_index(
        "ix_ss__subj_eff_date",
        "strategy_signal",
        ["subject_type", "subject_key", "effective_date"],
        unique=False,
    )
    op.create_index(
        "ix_ss__run_id",
        "strategy_signal",
        ["run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ss__run_id", table_name="strategy_signal")
    op.drop_index("ix_ss__subj_eff_date", table_name="strategy_signal")
    op.drop_index("ix_ss__instr_eff_date", table_name="strategy_signal")
    op.drop_index("ix_ss__eff_date", table_name="strategy_signal")
    op.drop_index("ix_ss__ver_date", table_name="strategy_signal")
    op.drop_table("strategy_signal")