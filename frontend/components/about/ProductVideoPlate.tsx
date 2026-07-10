"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { useReducedMotion } from "framer-motion";
import { Pause, Play } from "lucide-react";

import { DETAIL_PANEL_ID } from "./details";

const PRODUCT_SHOTS = [
  {
    id: "resume",
    src: "/videos/teamscout-match-01.mp4",
    poster: "/videos/teamscout-match-01-poster.jpg",
    fig: "Fig. 1a",
    caption: "Resume card — structured profile from an upload",
  },
  {
    id: "matches",
    src: "/videos/teamscout-match-02.mp4",
    poster: "/videos/teamscout-match-02-poster.jpg",
    fig: "Fig. 1b",
    caption: "Ranked fits — multi-signal scores with transparent breakdown",
  },
  {
    id: "team",
    src: "/videos/teamscout-match-03.mp4",
    poster: "/videos/teamscout-match-03-poster.jpg",
    fig: "Fig. 1c",
    caption: "Hiring-team constellation — who to reach after the match",
  },
] as const;

export default function ProductVideoPlate({
  selected,
  onSelect,
}: {
  selected: boolean;
  onSelect: (el: HTMLElement | null) => void;
}) {
  const reduced = useReducedMotion();
  const videoRef = useRef<HTMLVideoElement>(null);
  const playRetryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wantPlayRef = useRef(true);
  const [shotIndex, setShotIndex] = useState(0);
  const [userWantsPlay, setUserWantsPlay] = useState(true);

  const shot = PRODUCT_SHOTS[shotIndex] ?? PRODUCT_SHOTS[0];

  const setWantPlay = useCallback((want: boolean) => {
    wantPlayRef.current = want;
    setUserWantsPlay(want);
  }, []);

  const clearPlayRetry = useCallback(() => {
    if (playRetryRef.current != null) {
      clearTimeout(playRetryRef.current);
      playRetryRef.current = null;
    }
  }, []);

  const tryPlay = useCallback(() => {
    const el = videoRef.current;
    if (!el || reduced || !wantPlayRef.current) return;
    void el.play().catch(() => {
      if (!wantPlayRef.current) return;
      if (playRetryRef.current != null) return;
      playRetryRef.current = setTimeout(() => {
        playRetryRef.current = null;
        const retryEl = videoRef.current;
        if (!retryEl || !wantPlayRef.current) return;
        void retryEl.play().catch(() => {
          setWantPlay(false);
        });
      }, 280);
    });
  }, [reduced, setWantPlay]);

  useEffect(() => {
    if (reduced || !wantPlayRef.current) return;
    tryPlay();
    return clearPlayRetry;
  }, [reduced, shotIndex, tryPlay, clearPlayRetry]);

  const advanceShot = useCallback(() => {
    setShotIndex((i) => (i + 1) % PRODUCT_SHOTS.length);
  }, []);

  const togglePlayback = useCallback(
    (e: ReactMouseEvent | ReactKeyboardEvent) => {
      e.stopPropagation();
      const el = videoRef.current;
      if (!el || reduced) return;
      if (wantPlayRef.current) {
        setWantPlay(false);
        clearPlayRetry();
        el.pause();
      } else {
        setWantPlay(true);
        tryPlay();
      }
    },
    [clearPlayRetry, reduced, setWantPlay, tryPlay],
  );

  return (
    <figure className="about-video-block">
      <div className="about-video-shell">
        <button
          type="button"
          className="about-video-frame"
          onClick={(e) => onSelect(e.currentTarget)}
          aria-label="Open details about the TeamScout product motion"
          aria-expanded={selected}
          aria-controls={selected ? DETAIL_PANEL_ID : undefined}
          data-testid="about-product-video"
        >
          {reduced ? (
            // eslint-disable-next-line @next/next/no-img-element -- static poster for reduced-motion
            <img
              className="about-video"
              src={PRODUCT_SHOTS[0].poster}
              alt=""
              width={1280}
              height={720}
            />
          ) : (
            <video
              key={shot.src}
              ref={videoRef}
              className="about-video"
              src={shot.src}
              poster={shot.poster}
              muted
              playsInline
              preload="auto"
              data-testid="about-product-video-el"
              data-shot={shot.id}
              onEnded={advanceShot}
              onCanPlay={() => {
                if (wantPlayRef.current) tryPlay();
              }}
            />
          )}
          <span className="about-video-shots" aria-hidden>
            {PRODUCT_SHOTS.map((s, i) => (
              <span
                key={s.id}
                className="about-video-shot-mark"
                data-active={(reduced ? i === 0 : i === shotIndex) ? "true" : "false"}
              />
            ))}
          </span>
        </button>
        {!reduced ? (
          <button
            type="button"
            className="about-video-playback"
            onClick={togglePlayback}
            aria-label={userWantsPlay ? "Pause product video" : "Play product video"}
            data-testid="about-product-video-playback"
          >
            {userWantsPlay ? <Pause size={16} aria-hidden /> : <Play size={16} aria-hidden />}
            <span>{userWantsPlay ? "Pause" : "Play"}</span>
          </button>
        ) : null}
      </div>
      <figcaption className="about-video-plate-label" aria-live="polite">
        <span className="about-video-fig">{reduced ? "Fig. 1" : shot.fig}</span>
        <span className="about-video-caption-text">
          {reduced
            ? "Product film — resume → ranked fits → hiring-team constellation"
            : shot.caption}
        </span>
        <span className="about-video-meta">
          {reduced
            ? "AI-generated · still frame (reduced motion)"
            : `AI-generated · shot ${shotIndex + 1} of ${PRODUCT_SHOTS.length} · not a live recording`}
        </span>
      </figcaption>
      <p className="meta about-video-note">
        Real scores come from the weighted pipeline below, gated by{" "}
        <code>scripts/eval_ranking.py</code> and <code>scripts/eval_fit_signals.py</code>.
      </p>
    </figure>
  );
}
