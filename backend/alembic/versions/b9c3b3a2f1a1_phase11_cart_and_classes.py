"""phase11_cart_and_classes

Revision ID: b9c3b3a2f1a1
Revises: 5c730bcf3484
Create Date: 2026-08-24

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b9c3b3a2f1a1'
down_revision = '5c730bcf3484'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # gyms: add pricing + has_classes
    op.add_column('gyms', sa.Column('gym_price_per_person', sa.Numeric(precision=10, scale=2), nullable=False, server_default=sa.text('0')))
    op.add_column('gyms', sa.Column('has_classes', sa.Boolean(), nullable=False, server_default=sa.text('0')))

    # classes
    op.create_table(
        'gym_classes',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('gym_id', sa.BigInteger(), nullable=False),
        sa.Column('class_name', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('image_path', sa.String(length=500), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['gym_id'], ['gyms.id'], name=op.f('fk_gym_classes_gym_id_gyms')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_gym_classes')),
    )
    op.create_index('ix_gym_classes_gym_id', 'gym_classes', ['gym_id'], unique=False)
    op.create_index('ix_gym_classes_is_active', 'gym_classes', ['is_active'], unique=False)

    op.create_table(
        'class_sessions',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('gym_class_id', sa.BigInteger(), nullable=False),
        sa.Column('session_date', sa.Date(), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.Column('maximum_capacity', sa.Integer(), nullable=False),
        sa.Column('booked_capacity', sa.Integer(), nullable=False),
        sa.Column('price_per_person', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['gym_class_id'], ['gym_classes.id'], name=op.f('fk_class_sessions_gym_class_id_gym_classes')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_class_sessions')),
    )
    op.create_index('ix_class_sessions_gym_class_id', 'class_sessions', ['gym_class_id'], unique=False)
    op.create_index('ix_class_sessions_session_date', 'class_sessions', ['session_date'], unique=False)
    op.create_index('ix_class_sessions_status', 'class_sessions', ['status'], unique=False)

    # special hours
    op.create_table(
        'gym_special_hours',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('gym_id', sa.BigInteger(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('open_time', sa.Time(), nullable=True),
        sa.Column('close_time', sa.Time(), nullable=True),
        sa.Column('is_closed', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['gym_id'], ['gyms.id'], name=op.f('fk_gym_special_hours_gym_id_gyms')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_gym_special_hours')),
    )
    op.create_index('ix_gym_special_hours_gym_id', 'gym_special_hours', ['gym_id'], unique=False)
    op.create_index('ix_gym_special_hours_date', 'gym_special_hours', ['date'], unique=False)

    # cart_items
    op.create_table(
        'cart_items',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('booking_type', sa.String(length=10), nullable=False),
        sa.Column('gym_id', sa.BigInteger(), nullable=False),
        sa.Column('class_session_id', sa.BigInteger(), nullable=True),
        sa.Column('booking_date', sa.Date(), nullable=False),
        sa.Column('preferred_start_time', sa.Time(), nullable=True),
        sa.Column('preferred_end_time', sa.Time(), nullable=True),
        sa.Column('member_count', sa.Integer(), nullable=False),
        sa.Column('price_per_person', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('total_price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_cart_items_user_id_users')),
        sa.ForeignKeyConstraint(['gym_id'], ['gyms.id'], name=op.f('fk_cart_items_gym_id_gyms')),
        sa.ForeignKeyConstraint(['class_session_id'], ['class_sessions.id'], name=op.f('fk_cart_items_class_session_id_class_sessions')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_cart_items')),
    )
    op.create_index('ix_cart_items_user_id', 'cart_items', ['user_id'], unique=False)
    op.create_index('ix_cart_items_status', 'cart_items', ['status'], unique=False)
    op.create_index('ix_cart_items_gym_id', 'cart_items', ['gym_id'], unique=False)
    op.create_index('ix_cart_items_booking_date', 'cart_items', ['booking_date'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_cart_items_booking_date', table_name='cart_items')
    op.drop_index('ix_cart_items_gym_id', table_name='cart_items')
    op.drop_index('ix_cart_items_status', table_name='cart_items')
    op.drop_index('ix_cart_items_user_id', table_name='cart_items')
    op.drop_table('cart_items')

    op.drop_index('ix_gym_special_hours_date', table_name='gym_special_hours')
    op.drop_index('ix_gym_special_hours_gym_id', table_name='gym_special_hours')
    op.drop_table('gym_special_hours')

    op.drop_index('ix_class_sessions_status', table_name='class_sessions')
    op.drop_index('ix_class_sessions_session_date', table_name='class_sessions')
    op.drop_index('ix_class_sessions_gym_class_id', table_name='class_sessions')
    op.drop_table('class_sessions')

    op.drop_index('ix_gym_classes_is_active', table_name='gym_classes')
    op.drop_index('ix_gym_classes_gym_id', table_name='gym_classes')
    op.drop_table('gym_classes')

    op.drop_column('gyms', 'has_classes')
    op.drop_column('gyms', 'gym_price_per_person')
