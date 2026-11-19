"""Indexed coordinate projection; preserves all original owner-entered values."""
import math
from alembic import op
import sqlalchemy as sa

revision = 'a13b4df67935'
down_revision = 'f02a3ce56824'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    op.add_column('gyms', sa.Column('geo_latitude', sa.Float(), nullable=True))
    op.add_column('gyms', sa.Column('geo_longitude', sa.Float(), nullable=True))
    gyms = sa.table('gyms', sa.column('id', sa.BigInteger()), sa.column('latitude', sa.String()),
                    sa.column('longitude', sa.String()), sa.column('geo_latitude', sa.Float()),
                    sa.column('geo_longitude', sa.Float()))
    last_id = 0
    while True:
        rows = bind.execute(sa.select(gyms.c.id, gyms.c.latitude, gyms.c.longitude)
                            .where(gyms.c.id > last_id).order_by(gyms.c.id).limit(500)).all()
        if not rows:
            break
        for gid, lat, lon in rows:
            try:
                lat, lon = float(lat), float(lon)
                valid = math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180
            except (ValueError, TypeError):
                valid = False
            if valid:
                bind.execute(gyms.update().where(gyms.c.id == gid).values(geo_latitude=lat, geo_longitude=lon))
        last_id = rows[-1][0]
    op.create_index('ix_gyms_discovery_geo', 'gyms', ['status', 'is_active', 'geo_latitude', 'geo_longitude'])


def downgrade():
    op.drop_index('ix_gyms_discovery_geo', table_name='gyms')
    op.drop_column('gyms', 'geo_longitude')
    op.drop_column('gyms', 'geo_latitude')