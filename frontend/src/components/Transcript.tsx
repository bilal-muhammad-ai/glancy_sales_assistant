import { usePipecatConversation } from "@pipecat-ai/client-react";

type MessagePart = {
  text?: string | { spoken?: string; unspoken?: string };
};

type ConversationMessage = {
  role?: string;
  parts?: MessagePart[];
};

function partText(part: MessagePart): string {
  const text = part.text;
  if (typeof text === "string") return text;
  if (text && typeof text === "object") {
    return `${text.spoken ?? ""}${text.unspoken ?? ""}`;
  }
  return "";
}

export default function Transcript() {
  const conversation = usePipecatConversation() as {
    messages?: ConversationMessage[];
  };
  const messages = conversation?.messages ?? [];

  return (
    <section className="transcript" aria-label="Conversation transcript">
      <h2>Transcript</h2>
      {messages.length === 0 ? (
        <p className="empty">Connected speech will appear here.</p>
      ) : (
        <ul>
          {messages.map((msg, i) => (
            <li key={i} className={msg.role === "user" ? "user" : "bot"}>
              <strong>{msg.role === "user" ? "You" : "Assistant"}</strong>
              <span>
                {(msg.parts ?? [])
                  .map(partText)
                  .filter(Boolean)
                  .join(" ")
                  .trim() || "…"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
