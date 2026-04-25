"use client";

import {
  Suspense,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Topbar } from "@/components/layout/Topbar";
import { Icon, type IconName } from "@/components/Icon";
import {
  ApiError,
  consultSearch,
  createSearch,
  type ConsultMessage,
} from "@/lib/api";
import { activeTeamId } from "@/lib/workspace";
import { useLocale, type TranslationKey } from "@/lib/i18n";

interface ChatMsg extends ConsultMessage {
  pending?: boolean;
}

const QUICK_PROMPT_KEYS: TranslationKey[] = [
  "search.prompts.0",
  "search.prompts.1",
  "search.prompts.2",
  "search.prompts.3",
];

export default function NewSearchPage() {
  return (
    <Suspense>
      <NewSearchInner />
    </Suspense>
  );
}

function NewSearchInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { t } = useLocale();

  const [niche, setNiche] = useState(searchParams.get("niche") ?? "");
  const [region, setRegion] = useState(searchParams.get("region") ?? "");
  const [idealCustomer, setIdealCustomer] = useState("");
  const [exclusions, setExclusions] = useState("");
  const [profession, setProfession] = useState("");

  // Marks which fields were last filled by Lumen (vs by the user). Used
  // to highlight the change so the user can see what the AI extracted.
  const [aiTouched, setAiTouched] = useState<Record<string, number>>({});
  const markAiTouched = (field: string) =>
    setAiTouched((prev) => ({ ...prev, [field]: Date.now() }));

  const [messages, setMessages] = useState<ChatMsg[]>([
    {
      role: "assistant",
      content: t("search.consult.greeting"),
    },
  ]);
  const [draft, setDraft] = useState("");
  const [thinking, setThinking] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [launching, setLaunching] = useState(false);
  const [readyToLaunch, setReadyToLaunch] = useState(false);
  const chatRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [messages, thinking]);

  const sendToLumen = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || thinking) return;
    setDraft("");
    setSubmitError(null);

    const nextHistory: ChatMsg[] = [
      ...messages,
      { role: "user", content: trimmed },
    ];
    setMessages(nextHistory);
    setThinking(true);

    try {
      const reply = await consultSearch(
        nextHistory.map(({ role, content }) => ({ role, content })),
      );

      // Update extracted fields. Don't clobber values the user typed
      // if Lumen returns null for that slot.
      if (reply.niche) {
        setNiche(reply.niche);
        markAiTouched("niche");
      }
      if (reply.region) {
        setRegion(reply.region);
        markAiTouched("region");
      }
      if (reply.ideal_customer) {
        setIdealCustomer(reply.ideal_customer);
        markAiTouched("ideal_customer");
      }
      if (reply.exclusions) {
        setExclusions(reply.exclusions);
        markAiTouched("exclusions");
      }
      setReadyToLaunch(reply.ready);

      setMessages((m) => [...m, { role: "assistant", content: reply.reply }]);
    } catch (e) {
      const detail =
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : String(e);
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: t("search.consult.error", { detail }),
        },
      ]);
    } finally {
      setThinking(false);
    }
  };

  const launch = async () => {
    if (!niche || !region) return;
    setSubmitError(null);
    setLaunching(true);
    try {
      const offerParts = [
        profession,
        idealCustomer
          ? `${t("search.form.ideal")}: ${idealCustomer}`
          : null,
        exclusions ? `${t("search.form.exclude")}: ${exclusions}` : null,
      ].filter(Boolean);
      const resp = await createSearch({
        niche,
        region,
        profession: offerParts.join(". ") || undefined,
        team_id: activeTeamId(),
      });
      router.push(`/app/sessions/${resp.id}`);
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : String(e));
      setLaunching(false);
    }
  };

  const launchDisabled = launching || !niche.trim() || !region.trim();

  return (
    <>
      <Topbar
        crumbs={[
          { label: t("search.crumb.workspace"), href: "/app" },
          { label: t("search.crumb.new") },
        ]}
        right={
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => router.push("/app")}
            type="button"
          >
            {t("common.cancel")}
          </button>
        }
      />
      <div
        className="page"
        style={{
          display: "grid",
          gridTemplateColumns: "1.15fr 1fr",
          gap: 24,
          maxWidth: 1240,
        }}
      >
        <ChatColumn
          messages={messages}
          thinking={thinking}
          draft={draft}
          onDraftChange={setDraft}
          onSubmit={() => sendToLumen(draft)}
          onPickPrompt={(key) => sendToLumen(t(key))}
          chatRef={chatRef}
        />

        <FormColumn
          niche={niche}
          region={region}
          idealCustomer={idealCustomer}
          exclusions={exclusions}
          profession={profession}
          aiTouched={aiTouched}
          onNicheChange={(v) => setNiche(v)}
          onRegionChange={(v) => setRegion(v)}
          onIdealCustomerChange={(v) => setIdealCustomer(v)}
          onExclusionsChange={(v) => setExclusions(v)}
          onProfessionChange={(v) => setProfession(v)}
          readyHint={readyToLaunch}
          onLaunch={launch}
          launching={launching}
          launchDisabled={launchDisabled}
          submitError={submitError}
        />
      </div>
    </>
  );
}

// ─── Chat column ────────────────────────────────────────────────────

function ChatColumn({
  messages,
  thinking,
  draft,
  onDraftChange,
  onSubmit,
  onPickPrompt,
  chatRef,
}: {
  messages: ChatMsg[];
  thinking: boolean;
  draft: string;
  onDraftChange: (v: string) => void;
  onSubmit: () => void;
  onPickPrompt: (key: TranslationKey) => void;
  chatRef: React.RefObject<HTMLDivElement>;
}) {
  const { t } = useLocale();

  return (
    <div
      className="card"
      style={{
        padding: 0,
        display: "flex",
        flexDirection: "column",
        height: "calc(100vh - 140px)",
        minHeight: 560,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          padding: "18px 22px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          gap: 12,
          background:
            "linear-gradient(135deg, color-mix(in srgb, var(--accent) 6%, var(--surface)), var(--surface))",
        }}
      >
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: "50%",
            background: "linear-gradient(135deg, var(--accent), #EC4899)",
            display: "grid",
            placeItems: "center",
            color: "white",
            flexShrink: 0,
          }}
        >
          <Icon name="sparkles" size={18} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 14, fontWeight: 700 }}>Lumen</div>
          <div
            style={{
              fontSize: 11,
              color: "var(--text-muted)",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <span
              className="status-dot live"
              style={{ width: 6, height: 6 }}
            />
            {thinking ? t("search.consult.thinking") : t("search.consult.role")}
          </div>
        </div>
      </div>

      <div
        ref={chatRef}
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "20px 22px",
          display: "flex",
          flexDirection: "column",
          gap: 14,
        }}
      >
        {messages.map((m, i) => (
          <ChatBubble key={i} msg={m} />
        ))}
        {thinking && <ThinkingBubble />}
        {messages.length === 1 && (
          <div style={{ marginTop: 8 }}>
            <div
              className="eyebrow"
              style={{ marginBottom: 10, fontSize: 10 }}
            >
              {t("search.chat.tryThese")}
            </div>
            <div
              style={{ display: "flex", flexDirection: "column", gap: 6 }}
            >
              {QUICK_PROMPT_KEYS.map((k) => (
                <button
                  key={k}
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => onPickPrompt(k)}
                  style={{ justifyContent: "flex-start" }}
                >
                  <Icon name="arrow" size={13} />
                  {t(k)}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div
        style={{
          padding: "14px 16px",
          borderTop: "1px solid var(--border)",
          display: "flex",
          gap: 8,
          background: "var(--surface)",
        }}
      >
        <input
          className="input"
          value={draft}
          onChange={(e) => onDraftChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSubmit();
            }
          }}
          placeholder={t("search.consult.placeholder")}
          disabled={thinking}
        />
        <button
          type="button"
          className="btn btn-icon"
          onClick={onSubmit}
          disabled={thinking || !draft.trim()}
          style={{
            background: "var(--accent)",
            color: "white",
            width: 40,
            height: 40,
            opacity: thinking || !draft.trim() ? 0.5 : 1,
          }}
        >
          <Icon name="send" size={16} />
        </button>
      </div>
    </div>
  );
}

function ChatBubble({ msg }: { msg: ChatMsg }) {
  const isBot = msg.role === "assistant";
  return (
    <div
      style={{
        display: "flex",
        gap: 10,
        alignItems: "flex-start",
        flexDirection: isBot ? "row" : "row-reverse",
      }}
    >
      {isBot ? (
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: "50%",
            background: "linear-gradient(135deg, var(--accent), #EC4899)",
            display: "grid",
            placeItems: "center",
            color: "white",
            flexShrink: 0,
          }}
        >
          <Icon name="sparkles" size={13} />
        </div>
      ) : (
        <div
          className="avatar avatar-sm"
          style={{ background: "var(--accent)" }}
        >
          ·
        </div>
      )}
      <div
        style={{
          maxWidth: "82%",
          padding: "10px 14px",
          background: isBot ? "var(--surface-2)" : "var(--accent)",
          color: isBot ? "var(--text)" : "white",
          border: isBot ? "1px solid var(--border)" : "none",
          borderRadius: 14,
          borderTopLeftRadius: isBot ? 4 : 14,
          borderTopRightRadius: isBot ? 14 : 4,
          fontSize: 13.5,
          lineHeight: 1.55,
          whiteSpace: "pre-wrap",
        }}
      >
        {msg.content}
      </div>
    </div>
  );
}

function ThinkingBubble() {
  return (
    <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
      <div
        style={{
          width: 28,
          height: 28,
          borderRadius: "50%",
          background: "linear-gradient(135deg, var(--accent), #EC4899)",
          display: "grid",
          placeItems: "center",
          color: "white",
          flexShrink: 0,
        }}
      >
        <Icon name="sparkles" size={13} />
      </div>
      <div
        style={{
          padding: "10px 14px",
          background: "var(--surface-2)",
          border: "1px solid var(--border)",
          borderRadius: 14,
          borderTopLeftRadius: 4,
          display: "flex",
          gap: 4,
          alignItems: "center",
        }}
      >
        <Dot delay={0} />
        <Dot delay={120} />
        <Dot delay={240} />
      </div>
    </div>
  );
}

function Dot({ delay }: { delay: number }) {
  return (
    <span
      style={{
        width: 6,
        height: 6,
        borderRadius: "50%",
        background: "var(--text-muted)",
        animation: `lumen-pulse 1s ${delay}ms infinite ease-in-out`,
      }}
    />
  );
}

// ─── Form column ────────────────────────────────────────────────────

function FormColumn({
  niche,
  region,
  idealCustomer,
  exclusions,
  profession,
  aiTouched,
  onNicheChange,
  onRegionChange,
  onIdealCustomerChange,
  onExclusionsChange,
  onProfessionChange,
  readyHint,
  onLaunch,
  launching,
  launchDisabled,
  submitError,
}: {
  niche: string;
  region: string;
  idealCustomer: string;
  exclusions: string;
  profession: string;
  aiTouched: Record<string, number>;
  onNicheChange: (v: string) => void;
  onRegionChange: (v: string) => void;
  onIdealCustomerChange: (v: string) => void;
  onExclusionsChange: (v: string) => void;
  onProfessionChange: (v: string) => void;
  readyHint: boolean;
  onLaunch: () => void;
  launching: boolean;
  launchDisabled: boolean;
  submitError: string | null;
}) {
  const { t } = useLocale();

  const filledCount = useMemo(() => {
    let n = 0;
    if (niche.trim()) n++;
    if (region.trim()) n++;
    if (idealCustomer.trim()) n++;
    if (exclusions.trim()) n++;
    if (profession.trim()) n++;
    return n;
  }, [niche, region, idealCustomer, exclusions, profession]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <style>{`
        @keyframes lumen-pulse {
          0%, 80%, 100% { opacity: 0.35; transform: scale(.85); }
          40% { opacity: 1; transform: scale(1); }
        }
        @keyframes lumen-flash {
          0% { background: color-mix(in srgb, var(--accent) 18%, transparent); }
          100% { background: var(--surface); }
        }
        .lumen-touched {
          animation: lumen-flash 1.2s ease-out;
        }
      `}</style>

      <div>
        <div
          className="eyebrow"
          style={{
            marginBottom: 4,
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          <span>{t("search.form.eyebrow")}</span>
          <span style={{ color: "var(--text-dim)", fontWeight: 500 }}>
            · {filledCount}/5
          </span>
        </div>
        <div
          style={{
            fontSize: 22,
            fontWeight: 700,
            letterSpacing: "-0.01em",
            marginBottom: 4,
          }}
        >
          {t("search.form.title")}
        </div>
        <div
          style={{
            fontSize: 13,
            color: "var(--text-muted)",
            lineHeight: 1.5,
          }}
        >
          {t("search.form.subtitle")}
        </div>
      </div>

      <FormCard
        icon="folder"
        label={t("search.form.niche")}
        hint={t("search.form.nicheHint")}
        required
        flashKey={aiTouched.niche}
      >
        <input
          className="input"
          value={niche}
          onChange={(e) => onNicheChange(e.target.value)}
          placeholder={t("search.form.nichePh")}
        />
      </FormCard>

      <FormCard
        icon="mapPin"
        label={t("search.form.region")}
        hint={t("search.form.regionHint")}
        required
        flashKey={aiTouched.region}
      >
        <input
          className="input"
          value={region}
          onChange={(e) => onRegionChange(e.target.value)}
          placeholder={t("search.form.regionPh")}
        />
      </FormCard>

      <FormCard
        icon="users"
        label={t("search.form.ideal")}
        hint={t("search.form.idealHint")}
        flashKey={aiTouched.ideal_customer}
      >
        <textarea
          className="textarea"
          rows={2}
          value={idealCustomer}
          onChange={(e) => onIdealCustomerChange(e.target.value)}
          placeholder={t("search.form.idealPh")}
        />
      </FormCard>

      <FormCard
        icon="x"
        label={t("search.form.exclude")}
        hint={t("search.form.excludeHint")}
        flashKey={aiTouched.exclusions}
      >
        <input
          className="input"
          value={exclusions}
          onChange={(e) => onExclusionsChange(e.target.value)}
          placeholder={t("search.form.excludePh")}
        />
      </FormCard>

      <FormCard
        icon="briefcase"
        label={t("search.form.offer")}
        hint={t("search.form.offerHint")}
      >
        <textarea
          className="textarea"
          rows={3}
          value={profession}
          onChange={(e) => onProfessionChange(e.target.value)}
          placeholder={t("search.form.offerPh")}
        />
      </FormCard>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "12px 14px",
          background: "var(--surface-2)",
          borderRadius: 10,
          border: "1px solid var(--border)",
          fontSize: 12.5,
          color: "var(--text-muted)",
        }}
      >
        <Icon name="zap" size={16} style={{ color: "var(--warm)" }} />
        <div style={{ flex: 1 }}>{t("search.form.meta")}</div>
      </div>

      {submitError && (
        <div style={{ fontSize: 13, color: "var(--cold)" }}>{submitError}</div>
      )}

      <button
        type="button"
        className="btn btn-lg"
        disabled={launchDisabled}
        onClick={onLaunch}
        style={{
          justifyContent: "center",
          opacity: launchDisabled ? 0.5 : 1,
          background: readyHint
            ? "linear-gradient(135deg, var(--accent), #EC4899)"
            : undefined,
          color: readyHint ? "white" : undefined,
          border: readyHint ? "none" : undefined,
        }}
      >
        <Icon name="sparkles" size={16} />
        {launching ? t("common.loading") : t("search.form.launch")}
      </button>
    </div>
  );
}

function FormCard({
  icon,
  label,
  hint,
  required,
  flashKey,
  children,
}: {
  icon: IconName;
  label: string;
  hint?: string;
  required?: boolean;
  flashKey?: number;
  children: React.ReactNode;
}) {
  const [flashClass, setFlashClass] = useState("");
  useEffect(() => {
    if (!flashKey) return;
    setFlashClass("lumen-touched");
    const id = setTimeout(() => setFlashClass(""), 1300);
    return () => clearTimeout(id);
  }, [flashKey]);

  const cardStyle: CSSProperties = {
    padding: 14,
    borderRadius: 12,
    border: "1px solid var(--border)",
    background: "var(--surface)",
    display: "flex",
    flexDirection: "column",
    gap: 10,
  };

  return (
    <div className={flashClass} style={cardStyle}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
        }}
      >
        <div
          style={{
            width: 24,
            height: 24,
            borderRadius: 6,
            background: "var(--surface-2)",
            display: "grid",
            placeItems: "center",
            color: "var(--text-muted)",
            flexShrink: 0,
          }}
        >
          <Icon name={icon} size={13} />
        </div>
        <div
          style={{
            fontSize: 13,
            fontWeight: 600,
            letterSpacing: "-0.005em",
          }}
        >
          {label}
        </div>
        {required && (
          <span
            style={{
              fontSize: 10,
              color: "var(--accent)",
              fontWeight: 600,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
            }}
          >
            ·
          </span>
        )}
        {hint && (
          <span
            style={{
              marginLeft: "auto",
              fontSize: 11,
              color: "var(--text-dim)",
            }}
          >
            {hint}
          </span>
        )}
      </div>
      {children}
    </div>
  );
}
