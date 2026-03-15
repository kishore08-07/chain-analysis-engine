import React, { useState, useCallback, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';

const OFFSET = 12; // px gap from trigger

export default function Tooltip({ text, children, placement = 'top' }) {
  const [visible, setVisible] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0 });
  const triggerRef = useRef(null);
  const tooltipRef = useRef(null);

  const position = useCallback(() => {
    if (!triggerRef.current) return;
    const r = triggerRef.current.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    // Default: above trigger, centred
    let top = r.top - OFFSET;
    let left = r.left + r.width / 2;

    // Tooltip width is capped at 280px — check right boundary
    const tipW = Math.min(280, vw - 32);
    if (left + tipW / 2 > vw - 16) left = vw - tipW / 2 - 16;
    if (left - tipW / 2 < 16) left = tipW / 2 + 16;

    setPos({ top, left });
  }, []);

  const show = useCallback(() => {
    position();
    setVisible(true);
  }, [position]);

  const hide = useCallback(() => setVisible(false), []);

  // Reposition on scroll/resize while visible
  useEffect(() => {
    if (!visible) return;
    window.addEventListener('scroll', hide, true);
    window.addEventListener('resize', hide);
    return () => {
      window.removeEventListener('scroll', hide, true);
      window.removeEventListener('resize', hide);
    };
  }, [visible, hide]);

  if (!text) return children || null;

  const isIcon = !children;

  return (
    <>
      <span
        ref={triggerRef}
        className={`tooltip-trigger${isIcon ? ' tooltip-icon-wrap' : ''}`}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        tabIndex={isIcon ? 0 : undefined}
        aria-label={isIcon ? 'More info' : undefined}
      >
        {isIcon ? <span className="tooltip-icon">?</span> : children}
      </span>

      {visible &&
        createPortal(
          <div
            ref={tooltipRef}
            className="tooltip-popup"
            style={{ top: pos.top, left: pos.left }}
            role="tooltip"
          >
            {text}
            <div className="tooltip-arrow" />
          </div>,
          document.body
        )}
    </>
  );
}
