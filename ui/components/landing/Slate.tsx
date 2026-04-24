import { SLATE_CARDS } from "@/lib/mock-data";

export function Slate() {
  return (
    <section className="slate" id="slate" aria-label="Today's slate">
      <div className="slate-head">
        <span className="section-num">/ A</span>
        <h2 className="slate-title">
          15 PARKS. ONE <span className="accent">NIGHT</span>.
        </h2>
        <p className="slate-kicker">
          Every game tonight, every micro-condition. Scroll sideways.
        </p>
      </div>
      <div className="slate-scroller">
        <div className="slate-track">
          {SLATE_CARDS.map((card, i) => (
            <article className="slate-card" key={`${card.away}-${card.home}-${i}`}>
              <div className="sc-time">{card.time}</div>
              <div className="sc-match">
                <span>{card.away}</span>
                <span className="at">@</span>
                <span>{card.home}</span>
              </div>
              <div className="sc-top">
                TOP PICK · <b>{card.topPick}</b>
              </div>
              <div className="sc-weather">
                <div className="sc-w">
                  <div className="sc-w-k">WIND</div>
                  <div className={`sc-w-v ${card.windText.startsWith("+") ? "accent" : ""}`}>
                    {card.windText}
                  </div>
                </div>
                <div className="sc-w">
                  <div className="sc-w-k">TEMP</div>
                  <div className="sc-w-v">{card.tempText}</div>
                </div>
                <div className="sc-w">
                  <div className="sc-w-k">PARK</div>
                  <div className={`sc-w-v ${card.parkText.startsWith("+") ? "accent" : ""}`}>
                    {card.parkText}
                  </div>
                </div>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
