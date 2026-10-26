// The 3D view of one model's place, for Reflex (cad_roam/components/world_view.py). The engine (engine.js)
// does everything; this mounts it, hands it the page's props and passes its events on.
import React, { useEffect, useRef } from "react";
import { Engine } from "./engine.js";

export function RoamWorld({ model, backend, me, spawn, command, labels, quality, onEvent }) {
  const box = useRef(null);
  const engine = useRef(null);
  const handler = useRef(onEvent);
  handler.current = onEvent;
  const peer = (me && me.peer) || "";

  useEffect(() => {
    if (!box.current || !model || !peer) return undefined;
    let eng;
    try {
      eng = new Engine(box.current, {
        model,
        backend,
        me,
        spawn,
        labels,
        quality,
        onEvent: (e) => handler.current && handler.current(e),
      });
    } catch (e) {
      console.error("Roam:", e);
      if (handler.current) handler.current({ type: "error", text: String(e && e.message ? e.message : e) });
      return undefined;
    }
    engine.current = eng;
    // What the page shows, for an AI in a dialog over it (reflex_ddns_auth.companion).
    const describe = () => eng.describe();
    window.__ddnsContext = describe;
    return () => {
      eng.dispose();
      if (engine.current === eng) engine.current = null;
      if (window.__ddnsContext === describe) delete window.__ddnsContext;
    };
    // Another model or another tab identity makes a new engine; the rest is passed in below.
  }, [model, peer, backend, quality]);

  useEffect(() => {
    if (engine.current) engine.current.opts.me = me;
  }, [me]);

  useEffect(() => {
    if (engine.current) engine.current.setLabels(labels);
  }, [labels]);

  const seq = command && command.seq;
  useEffect(() => {
    if (engine.current && command && command.type) engine.current.command(command);
  }, [seq]);

  return <div ref={box} className="rm-world" data-model={model} />;
}
