"""feature store: matchup_features partitioned table.

Revision ID: 0004_feature_store
Revises: 0003_operational_tables
Create Date: 2026-04-22

Wide feature row keyed by (game_date, game_pk, batter_id, pitcher_id).
Range-partitioned by game_date yearly to match statcast_pitches.
"""

from __future__ import annotations

from datetime import date

from alembic import op

revision = "0004_feature_store"
down_revision = "0003_operational_tables"
branch_labels = None
depends_on = None


PARTITION_START_YEAR = 2021


def _partition_end_year() -> int:
    return date.today().year + 1


def upgrade() -> None:
    _create_matchup_features_table()
    _create_yearly_partitions()
    _create_indexes()


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_matchup_features_historical")
    op.execute("DROP INDEX IF EXISTS idx_matchup_features_game_pk")
    op.execute("DROP INDEX IF EXISTS idx_matchup_features_pitcher_date")
    op.execute("DROP INDEX IF EXISTS idx_matchup_features_batter_date")
    for year in range(PARTITION_START_YEAR, _partition_end_year() + 1):
        op.execute(f"DROP TABLE IF EXISTS matchup_features_{year}")
    op.execute("DROP TABLE IF EXISTS matchup_features")


def _create_matchup_features_table() -> None:
    op.execute("""
        CREATE TABLE matchup_features (
            -- Keys
            game_date DATE NOT NULL,
            game_pk INTEGER NOT NULL,
            batter_id INTEGER NOT NULL,
            pitcher_id INTEGER NOT NULL,
            is_historical BOOLEAN NOT NULL DEFAULT FALSE,
            hr_on_pa BOOLEAN,

            -- Batter rolling windows (7d / 14d / 30d / season)
            b_barrel_pct_7d DOUBLE PRECISION,
            b_barrel_pct_14d DOUBLE PRECISION,
            b_barrel_pct_30d DOUBLE PRECISION,
            b_barrel_pct_season DOUBLE PRECISION,
            b_hardhit_pct_7d DOUBLE PRECISION,
            b_hardhit_pct_14d DOUBLE PRECISION,
            b_hardhit_pct_30d DOUBLE PRECISION,
            b_hardhit_pct_season DOUBLE PRECISION,
            b_avg_ev_7d DOUBLE PRECISION,
            b_avg_ev_14d DOUBLE PRECISION,
            b_avg_ev_30d DOUBLE PRECISION,
            b_avg_ev_season DOUBLE PRECISION,
            b_p90_ev_7d DOUBLE PRECISION,
            b_p90_ev_14d DOUBLE PRECISION,
            b_p90_ev_30d DOUBLE PRECISION,
            b_p90_ev_season DOUBLE PRECISION,
            b_avg_la_7d DOUBLE PRECISION,
            b_avg_la_14d DOUBLE PRECISION,
            b_avg_la_30d DOUBLE PRECISION,
            b_avg_la_season DOUBLE PRECISION,
            b_sweet_spot_pct_7d DOUBLE PRECISION,
            b_sweet_spot_pct_14d DOUBLE PRECISION,
            b_sweet_spot_pct_30d DOUBLE PRECISION,
            b_sweet_spot_pct_season DOUBLE PRECISION,
            b_pulled_fb_pct_7d DOUBLE PRECISION,
            b_pulled_fb_pct_14d DOUBLE PRECISION,
            b_pulled_fb_pct_30d DOUBLE PRECISION,
            b_pulled_fb_pct_season DOUBLE PRECISION,
            b_xwobacon_7d DOUBLE PRECISION,
            b_xwobacon_14d DOUBLE PRECISION,
            b_xwobacon_30d DOUBLE PRECISION,
            b_xwobacon_season DOUBLE PRECISION,
            b_xiso_7d DOUBLE PRECISION,
            b_xiso_14d DOUBLE PRECISION,
            b_xiso_30d DOUBLE PRECISION,
            b_xiso_season DOUBLE PRECISION,
            b_hr_per_pa_7d DOUBLE PRECISION,
            b_hr_per_pa_14d DOUBLE PRECISION,
            b_hr_per_pa_30d DOUBLE PRECISION,
            b_hr_per_pa_season DOUBLE PRECISION,
            b_pa_count_7d INTEGER,
            b_pa_count_14d INTEGER,
            b_pa_count_30d INTEGER,
            b_pa_count_season INTEGER,

            -- Batter platoon splits
            b_vs_lhp_barrel_pct DOUBLE PRECISION,
            b_vs_rhp_barrel_pct DOUBLE PRECISION,
            b_vs_lhp_xwoba DOUBLE PRECISION,
            b_vs_rhp_xwoba DOUBLE PRECISION,
            b_vs_lhp_hr_per_pa DOUBLE PRECISION,
            b_vs_rhp_hr_per_pa DOUBLE PRECISION,
            b_vs_lhp_hr_per_pa_reg DOUBLE PRECISION,
            b_vs_rhp_hr_per_pa_reg DOUBLE PRECISION,
            b_vs_lhp_pa_count INTEGER,
            b_vs_rhp_pa_count INTEGER,

            -- Batter vs pitch-type (2-season window)
            b_xwoba_vs_ff DOUBLE PRECISION,
            b_xwoba_vs_si DOUBLE PRECISION,
            b_xwoba_vs_fc DOUBLE PRECISION,
            b_xwoba_vs_sl DOUBLE PRECISION,
            b_xwoba_vs_cu DOUBLE PRECISION,
            b_xwoba_vs_ch DOUBLE PRECISION,
            b_xwoba_vs_fs DOUBLE PRECISION,
            b_hr_rate_vs_ff DOUBLE PRECISION,
            b_hr_rate_vs_si DOUBLE PRECISION,
            b_hr_rate_vs_fc DOUBLE PRECISION,
            b_hr_rate_vs_sl DOUBLE PRECISION,
            b_hr_rate_vs_cu DOUBLE PRECISION,
            b_hr_rate_vs_ch DOUBLE PRECISION,
            b_hr_rate_vs_fs DOUBLE PRECISION,
            b_pa_count_vs_ff INTEGER,
            b_pa_count_vs_si INTEGER,
            b_pa_count_vs_fc INTEGER,
            b_pa_count_vs_sl INTEGER,
            b_pa_count_vs_cu INTEGER,
            b_pa_count_vs_ch INTEGER,
            b_pa_count_vs_fs INTEGER,

            -- Batter bat-tracking (2024+)
            b_avg_bat_speed DOUBLE PRECISION,
            b_squared_up_pct DOUBLE PRECISION,
            b_blast_rate DOUBLE PRECISION,

            -- Pitcher profile
            p_hr_per_9_season DOUBLE PRECISION,
            p_hr_per_9_career DOUBLE PRECISION,
            p_barrel_pct_allowed_season DOUBLE PRECISION,
            p_hardhit_pct_allowed_season DOUBLE PRECISION,
            p_fb_pct DOUBLE PRECISION,
            p_gb_pct DOUBLE PRECISION,
            p_k_pct DOUBLE PRECISION,
            p_bb_pct DOUBLE PRECISION,

            -- Pitcher handedness splits
            p_vs_lhb_xwoba_allowed DOUBLE PRECISION,
            p_vs_rhb_xwoba_allowed DOUBLE PRECISION,
            p_vs_lhb_hr_rate DOUBLE PRECISION,
            p_vs_rhb_hr_rate DOUBLE PRECISION,

            -- Pitcher pitch mix & velocity
            p_ff_usage DOUBLE PRECISION,
            p_si_usage DOUBLE PRECISION,
            p_fc_usage DOUBLE PRECISION,
            p_sl_usage DOUBLE PRECISION,
            p_cu_usage DOUBLE PRECISION,
            p_ch_usage DOUBLE PRECISION,
            p_fs_usage DOUBLE PRECISION,
            p_ff_velo_avg DOUBLE PRECISION,
            p_primary_pitch VARCHAR(5),

            -- Pitcher TTO
            p_tto_penalty DOUBLE PRECISION,

            -- Bullpen (opposing team)
            bp_barrel_pct_allowed_season DOUBLE PRECISION,
            bp_hr_per_9_season DOUBLE PRECISION,

            -- Park factors
            park_hr_factor_hand DOUBLE PRECISION,
            park_hr_factor_hand_3yr DOUBLE PRECISION,
            park_id INTEGER,
            park_elevation_ft INTEGER,

            -- Weather
            wx_temperature_f DOUBLE PRECISION,
            wx_humidity_pct DOUBLE PRECISION,
            wx_pressure_hpa DOUBLE PRECISION,
            wx_air_density_relative DOUBLE PRECISION,
            wx_wind_speed_mph DOUBLE PRECISION,
            wx_wind_carry_lf DOUBLE PRECISION,
            wx_wind_carry_cf DOUBLE PRECISION,
            wx_wind_carry_rf DOUBLE PRECISION,
            wx_is_roof_closed BOOLEAN,

            -- Context
            ctx_batting_order SMALLINT,
            ctx_projected_pa DOUBLE PRECISION,
            ctx_day_night VARCHAR(1),
            ctx_is_home BOOLEAN,
            ctx_batter_days_rest INTEGER,
            ctx_pitcher_days_rest INTEGER,
            ctx_same_hand BOOLEAN,

            -- Audit
            built_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            PRIMARY KEY (game_date, game_pk, batter_id, pitcher_id)
        ) PARTITION BY RANGE (game_date)
        """)


def _create_yearly_partitions() -> None:
    end = _partition_end_year()
    for year in range(PARTITION_START_YEAR, end + 1):
        op.execute(f"""
            CREATE TABLE matchup_features_{year}
            PARTITION OF matchup_features
            FOR VALUES FROM ('{year}-01-01') TO ('{year + 1}-01-01')
            """)


def _create_indexes() -> None:
    op.execute(
        "CREATE INDEX idx_matchup_features_batter_date "
        "ON matchup_features (batter_id, game_date DESC)"
    )
    op.execute(
        "CREATE INDEX idx_matchup_features_pitcher_date "
        "ON matchup_features (pitcher_id, game_date DESC)"
    )
    op.execute("CREATE INDEX idx_matchup_features_game_pk ON matchup_features (game_pk)")
    op.execute(
        "CREATE INDEX idx_matchup_features_historical "
        "ON matchup_features (game_date DESC) WHERE is_historical = true"
    )
