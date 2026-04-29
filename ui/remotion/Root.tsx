import { Composition, Still } from "remotion";
import { HomerunPromo, PosterFrame } from "./HomerunPromo";

export const PROMO_FPS = 30;
export const PROMO_WIDTH = 1080;
export const PROMO_HEIGHT = 1920;
export const PROMO_DURATION_FRAMES = PROMO_FPS * 15;

export const RemotionRoot = () => (
  <>
    <Composition
      id="HomerunPromo"
      component={HomerunPromo}
      durationInFrames={PROMO_DURATION_FRAMES}
      fps={PROMO_FPS}
      width={PROMO_WIDTH}
      height={PROMO_HEIGHT}
      defaultProps={{
        slateDate: "TODAY'S MLB SLATE",
        modelVersion: "v20260423_231941",
      }}
    />
    <Still
      id="HomerunPromoPoster"
      component={PosterFrame}
      width={PROMO_WIDTH}
      height={PROMO_HEIGHT}
      defaultProps={{
        slateDate: "TODAY'S MLB SLATE",
        modelVersion: "v20260423_231941",
      }}
    />
  </>
);
