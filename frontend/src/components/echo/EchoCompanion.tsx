import React, { useEffect, useRef, useState } from 'react';
import idleAsset from '../../assets/echo/idle.png';
import curiousAsset from '../../assets/echo/curious.png';
import thinkingAsset from '../../assets/echo/thinking.png';
import workingAsset from '../../assets/echo/working.png';
import happyAsset from '../../assets/echo/happy.png';
import confusedAsset from '../../assets/echo/confused.png';
import sleepyAsset from '../../assets/echo/sleepy.png';
import disconnectedAsset from '../../assets/echo/disconnected.png';
import { EchoState, echoStateLabel } from './echoState';

const assets: Record<EchoState, string> = {
  IDLE: idleAsset,
  CURIOUS: curiousAsset,
  THINKING: thinkingAsset,
  WORKING: workingAsset,
  HAPPY: happyAsset,
  CONFUSED: confusedAsset,
  SLEEPY: sleepyAsset,
  DISCONNECTED: disconnectedAsset,
};

interface EchoCompanionProps {
  state: EchoState;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
  draggable?: boolean;
}

interface TransitionState {
  from: EchoState;
  token: number;
}

const sizeMap = {
  sm: '9rem',
  md: '12rem',
  lg: '15rem',
};

export const EchoCompanion: React.FC<EchoCompanionProps> = ({
  state,
  className = '',
  size = 'sm',
  draggable = true,
}) => {
  const previousState = useRef(state);
  const transitionToken = useRef(0);
  const [transition, setTransition] = useState<TransitionState | null>(null);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const dragStart = useRef<{ x: number; y: number; offsetX: number; offsetY: number } | null>(null);

  useEffect(() => {
    if (previousState.current === state) return;
    const token = ++transitionToken.current;
    setTransition({ from: previousState.current, token });
    previousState.current = state;
    const timer = window.setTimeout(() => {
      setTransition((current) => (current?.token === token ? null : current));
    }, 180);
    return () => window.clearTimeout(timer);
  }, [state]);

  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!draggable) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragStart.current = {
      x: event.clientX,
      y: event.clientY,
      offsetX: offset.x,
      offsetY: offset.y,
    };
  };

  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!dragStart.current) return;
    setOffset({
      x: dragStart.current.offsetX + event.clientX - dragStart.current.x,
      y: dragStart.current.offsetY + event.clientY - dragStart.current.y,
    });
  };

  const handlePointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    dragStart.current = null;
  };

  return (
    <div
      className={`echo-companion echo-companion--${state.toLowerCase()} ${className}`}
      style={{ width: sizeMap[size], transform: `translate3d(${offset.x}px, ${offset.y}px, 0)` }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
      role="img"
      aria-label={`ECHO: ${echoStateLabel(state)}`}
      title={`ECHO — ${echoStateLabel(state)}`}
    >
      <div className="echo-companion__frame">
        {transition && (
          <img
            className="echo-companion__art echo-companion__art--outgoing"
            src={assets[transition.from]}
            alt=""
            aria-hidden="true"
            draggable={false}
          />
        )}
        <img
          className="echo-companion__art"
          src={assets[state]}
          alt=""
          aria-hidden="true"
          draggable={false}
        />
      </div>
    </div>
  );
};
