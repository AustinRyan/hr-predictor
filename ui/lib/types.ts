/**
 * API types mirroring src/api/schemas/ (Pydantic) one-to-one.
 * Keep this in lockstep with the backend — add a field here first,
 * then use it in a component.
 */

export type FeatureContribution = {
  name: string;
  contribution: number;
};

export type PickSummary = {
  batter_id: number;
  batter_name: string | null;
  batter_bats: string | null;
  batter_position: string | null;
  team_abbr: string | null;

  game_pk: number;
  game_date: string; // ISO date
  game_start_utc: string | null;
  park_name: string | null;
  home_team_abbr: string | null;
  away_team_abbr: string | null;

  pitcher_id: number;
  pitcher_name: string | null;
  pitcher_throws: string | null;

  prob_at_least_one_hr: number;
  expected_hrs: number | null;

  barrel_pct_season: number | null;
  p90_ev_season: number | null;
  park_hr_factor_hand: number | null;
  pitcher_hr_per_9_season: number | null;
  pitcher_barrel_pct_allowed_season: number | null;
  batting_order: number | null;
  projected_pas: number | null;
  wind_carry_cf: number | null;
  temperature_f: number | null;
  air_density_relative: number | null;

  top_contributing_features: FeatureContribution[];

  model_version: string;
};

export type PlayerProfile = {
  mlbam_id: number;
  full_name: string | null;
  first_name: string | null;
  last_name: string | null;
  bats: string | null;
  throws: string | null;
  primary_position: string | null;
  active: boolean;
};

export type PlayerRollingStats = {
  as_of: string | null;
  b_barrel_pct_30d: number | null;
  b_hardhit_pct_30d: number | null;
  b_avg_ev_30d: number | null;
  b_p90_ev_30d: number | null;
  b_avg_la_30d: number | null;
  b_pulled_fb_pct_30d: number | null;
  b_xwobacon_30d: number | null;
  b_hr_per_pa_30d: number | null;
  b_pa_count_30d: number | null;
  b_barrel_pct_season: number | null;
  b_hr_per_pa_season: number | null;
  b_pa_count_season: number | null;
};

export type PlayerTodayPrediction = {
  game_pk: number;
  pitcher_id: number;
  prob_at_least_one_hr: number;
  expected_hrs: number | null;
  projected_pas: number | null;
  model_version: string;
};

export type PlayerDetail = {
  profile: PlayerProfile;
  rolling: PlayerRollingStats;
  today_prediction: PlayerTodayPrediction | null;
};

export type BatterProfile = {
  mlbam_id: number;
  full_name: string | null;
  bats: string | null;
  b_barrel_pct_season: number | null;
  b_p90_ev_season: number | null;
  b_avg_ev_season: number | null;
  b_pulled_fb_pct_season: number | null;
  b_hr_per_pa_season: number | null;
  b_vs_lhp_hr_per_pa_reg: number | null;
  b_vs_rhp_hr_per_pa_reg: number | null;
  b_pa_count_season: number | null;
};

export type PitcherProfile = {
  mlbam_id: number;
  full_name: string | null;
  throws: string | null;
  p_hr_per_9_season: number | null;
  p_barrel_pct_allowed_season: number | null;
  p_vs_lhb_hr_rate: number | null;
  p_vs_rhb_hr_rate: number | null;
  p_primary_pitch: string | null;
  p_ff_velo_avg: number | null;
  p_tto_penalty: number | null;
};

export type ParkContext = {
  park_id: number | null;
  park_name: string | null;
  elevation_ft: number | null;
  roof_type: string | null;
  park_hr_factor_hand: number | null;
  park_hr_factor_hand_3yr: number | null;
};

export type WeatherContext = {
  temperature_f: number | null;
  humidity_pct: number | null;
  wind_speed_mph: number | null;
  wind_direction_deg: number | null;
  air_density_relative: number | null;
  wind_carry_lf: number | null;
  wind_carry_cf: number | null;
  wind_carry_rf: number | null;
  is_roof_closed: boolean | null;
};

export type GameContext = {
  game_pk: number;
  game_date: string;
  game_start_utc: string | null;
  home_team_abbr: string | null;
  away_team_abbr: string | null;
  ctx_batting_order: number | null;
  ctx_projected_pa: number | null;
  ctx_is_home: boolean | null;
  ctx_day_night: string | null;
  ctx_same_hand: boolean | null;
};

export type PredictionBreakdown = {
  prob_at_least_one_hr: number | null;
  prob_at_least_two_hr: number | null;
  expected_hrs: number | null;
  starter_raw_prob: number | null;
  starter_calibrated_prob: number | null;
  bullpen_raw_prob: number | null;
  bullpen_calibrated_prob: number | null;
  top_contributing_features: FeatureContribution[];
  model_version: string | null;
  generated_at: string | null;
};

export type MatchupDetail = {
  game: GameContext;
  batter: BatterProfile;
  pitcher: PitcherProfile;
  park: ParkContext;
  weather: WeatherContext;
  prediction: PredictionBreakdown | null;
};

export type TrainingMetadata = {
  model_version: string;
  git_sha: string | null;
  data_hash: string | null;
  training_range: [string, string] | string[];
  num_features: number;
  created_at_utc: string | null;
  config: Record<string, unknown>;
};

export type TrainingMetrics = {
  train_log_loss: number | null;
  val_log_loss: number | null;
  test_log_loss: number | null;
  train_brier: number | null;
  val_brier: number | null;
  test_brier: number | null;
  test_auc: number | null;
  test_ece: number | null;
  test_precision_at_top_k: number | null;
};

export type ReliabilityBin = {
  bin_lower: number;
  bin_upper: number;
  mean_pred: number | null;
  actual_rate: number | null;
  count: number;
};

export type RollingLiveMetrics = {
  window_days: number;
  n_predictions: number;
  evaluated_from: string | null;
  evaluated_to: string | null;
  log_loss: number | null;
  brier: number | null;
  ece: number | null;
  reliability: ReliabilityBin[];
};

export type ModelMetricsResponse = {
  training_metadata: TrainingMetadata;
  training_metrics: TrainingMetrics;
  rolling_live: RollingLiveMetrics;
};
