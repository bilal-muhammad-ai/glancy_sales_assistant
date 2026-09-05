import { useCallback, useState } from "react";
import { RTVIEvent } from "@pipecat-ai/client-js";
import {
  usePipecatClient,
  usePipecatClientTransportState,
  useRTVIClientEvent,
} from "@pipecat-ai/client-react";
import Transcript from "./components/Transcript";

const BOT_OFFER_URL =
  import.meta.env.VITE_BOT_OFFER_URL?.trim() || "/api/offer";

export default function App() {
  const client = usePipecatClient();
  const transportState = usePipecatClientTransportState();
  const [error, setError] = useState<string | null>(null);

  const isConnected = transportState === "ready";
  const isConnecting = ["authenticating", "connecting", "connected"].includes(
    transportState,
  );

  useRTVIClientEvent(
    RTVIEvent.Error,
    useCallback((err: unknown) => {
      console.error("Bot error:", err);
      const message =
        err && typeof err === "object" && "message" in err
          ? String((err as { message: unknown }).message)
          : "Something went wrong with the voice connection.";
      setError(message);
    }, []),
  );

  const handleConnect = async () => {
    if (!client) return;
    setError(null);
    try {
      await client.connect({
        webrtcRequestParams: { endpoint: BOT_OFFER_URL },
      });
    } catch (err) {
      console.error(err);
      const message =
        err instanceof Error
          ? err.message
          : "Could not connect. Is the voice bot running on port 7860?";
      setError(message);
    }
  };

  const handleDisconnect = async () => {
    if (!client) return;
    setError(null);
    try {
      await client.disconnect();
    } catch (err) {
      console.error(err);
      setError(err instanceof Error ? err.message : "Disconnect failed.");
    }
  };

  return (
    <div className="page">
      <header className="hero">
        <p className="brand">Glancy</p>
        <h1 className="headline">Voice assistant</h1>
        <p className="subhead">
          Talk to the Glancy Fawcett knowledge base. Allow the microphone when
          prompted.
        </p>

        <div className="controls">
          <button
            type="button"
            className="cta"
            onClick={isConnected ? handleDisconnect : handleConnect}
            disabled={isConnecting || !client}
          >
            {isConnected
              ? "Disconnect"
              : isConnecting
                ? "Connecting…"
                : "Connect"}
          </button>
          <p className="status" aria-live="polite">
            Status: <span>{transportState}</span>
          </p>
        </div>

        {error ? <p className="error">{error}</p> : null}
      </header>

      <Transcript />
    </div>
  );
}
