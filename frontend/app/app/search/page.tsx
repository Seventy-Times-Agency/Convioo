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
import { HenryAvatar } from "@/components/HenryAvatar";
import {
  ApiError,
  DEFAULT_LEAD_LIMIT,
  LEAD_LIMIT_CHOICES,
  RADIUS_CHOICES_KM,
  SEARCH_SCOPES,
  consultSearch,
  createSearch,
  getMyProfile,
  preflightSearch,
  suggestSearchAxes,
  type ConsultMessage,
  type ConsultSlot,
  type LeadLimitChoice,
  type PriorTeamSearch,
  type RadiusChoiceKm,
  type SearchAxisOption,
  type SearchScope,
  type UserProfile,
} from "@/lib/api";
import { NicheCombobox } from "@/components/app/NicheCombobox";
import { RegionCombobox } from "@/components/app/RegionCombobox";
import Link from "next/link";
import { activeTeamId } from "@/lib/workspace";
import { useLocale } from "@/lib/i18n";

interface ChatMsg extends ConsultMessage {
  pending?: boolean;
}

type OfferSource = "profile" | "custom";

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
  const [targetLanguages, setTargetLanguages] = useState<string[]>([]);
  const [leadLimit, setLeadLimit] = useState<LeadLimitChoice>(DEFAULT_LEAD_LIMIT);
  const [scope, setScope] = useState<SearchScope>("city");
  const [radiusKm, setRadiusKm] = useState<RadiusChoiceKm>(25);

  // Profile drives the "use my profile / custom" offer toggle. Loaded
  // once on mount; when present, that's the default source so the user
  // doesn't retype what's already on file.
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [offerSource, setOfferSource] = useState<OfferSource>("custom");

  // Marks which fields were last filled by Henry (vs by the user). Used
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
  // Slot Henry was waiting on after his most recent turn. Echoed back
  // to the backend on the next user message so a short reply lands in
  // the correct slot instead of being guessed.
  const [lastAskedSlot, setLastAskedSlot] = useState<ConsultSlot | null>(null);
  const [draft, setDraft] = useState("");
  const [thinking, setThinking] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [launching, setLaunching] = useState(false);
  const [readyToLaunch, setReadyToLaunch] = useState(false);
  const [duplicateMatches, setDuplicateMatches] = useState<PriorTeamSearch[]>([]);
  // "Подобрать с Henry" — Henry-proposed full search configurations.
  const [axesOptions, setAxesOptions] = useState<SearchAxisOption[] | null>(
    null,
  );
  const [axesLoading, setAxesLoading] = useState(false);
  const [axesError, setAxesError] = useState<string | null>(null);
  const chatRef = useRef<HTMLDivElement>(null);

  const fetchAxes = async () => {
    setAxesLoading(true);
    setAxesError(null);
    try {
      const res = await suggestSearchAxes();
      setAxesOptions(res.options);
    } catch (e) {
      setAxesError(e instanceof Error ? e.message : String(e));
    } finally {
      setAxesLoading(false);
    }
  };

  const applyAxis = (opt: SearchAxisOption) => {
    setNiche(opt.niche);
    setRegion(opt.region);
    if (opt.ideal_customer) setIdealCustomer(opt.ideal_customer);
    if (opt.exclusions) setExclusions(opt.exclusions);
    markAiTouched("niche");
    markAiTouched("region");
    if (opt.ideal_customer) markAiTouched("ideal_customer");
    if (opt.exclusions) markAiTouched("exclusions");
    // Hide the suggestion deck after applying so the user sees the
    // updated form clearly. They can re-open with the button.
    setAxesOptions(null);
  };

  const teamId = activeTeamId();

  useEffect(() => {
    let cancelled = false;
    getMyProfile()
      .then((p) => {
        if (cancelled) return;
        setProfile(p);
        if (p.service_description?.trim()) {
          setOfferSource("profile");
        }
        // Personalised greeting: replace the generic "расскажите кого
        // ищете" with one that references the niches / region / offer
        // already on the profile, so Henry doesn't ask things he
        // already knows. Only fires while the chat is still pristine
        // (one bot message, no user replies yet).
        setMessages((prev) => {
          if (prev.length !== 1 || prev[0].role !== "assistant") return prev;
          const niches = (p.niches ?? []).slice(0, 3);
          const region = (p.home_region ?? "").trim();
          const offer = (
            p.profession ??
            p.service_description ??
            ""
          ).trim();
          let greeting = t("search.consult.greeting");
          if (niches.length > 0 && region) {
            greeting = t("search.consult.greetingNichesRegion", {
              niches: niches.join(", "),
              region,
            });
          } else if (niches.length > 0) {
            greeting = t("search.consult.greetingNiches", {
              niches: niches.join(", "),
            });
          } else if (region && offer) {
            greeting = t("search.consult.greetingRegionOffer", {
              region,
            });
          }
          return [{ role: "assistant", content: greeting }];
        });
      })
      .catch(() => {
        // Profile fetch failure is non-fatal — fall through to the
        // custom-text variant of the offer block.
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  // Hard rule: in team mode, the same niche+region can't be re-run.
  // Preflight against the backend whenever the combo settles down so
  // the launch button can be disabled before the user clicks it.
  useEffect(() => {
    if (!teamId || !niche.trim() || !region.trim()) {
      setDuplicateMatches([]);
      return;
    }
    let cancelled = false;
    const handle = window.setTimeout(() => {
      preflightSearch({ niche, region, teamId })
        .then((r) => {
          if (!cancelled) setDuplicateMatches(r.matches);
        })
        .catch(() => {
          if (!cancelled) setDuplicateMatches([]);
        });
    }, 350);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [teamId, niche, region]);

  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [messages, thinking]);

  const sendToHenry = async (text: string) => {
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
        {
          niche: niche || null,
          region: region || null,
          ideal_customer: idealCustomer || null,
          exclusions: exclusions || null,
          last_asked_slot: lastAskedSlot,
        },
      );

      // Update extracted fields. Don't clobber values the user typed
      // if Henry returns null for that slot.
      if (reply.niche && reply.niche !== niche) {
        setNiche(reply.niche);
        markAiTouched("niche");
      }
      if (reply.region && reply.region !== region) {
        setRegion(reply.region);
        markAiTouched("region");
      }
      if (reply.ideal_customer && reply.ideal_customer !== idealCustomer) {
        setIdealCustomer(reply.ideal_customer);
        markAiTouched("ideal_customer");
      }
      if (reply.exclusions && reply.exclusions !== exclusions) {
        setExclusions(reply.exclusions);
        markAiTouched("exclusions");
      }
      setReadyToLaunch(reply.ready);
      setLastAskedSlot(reply.last_asked_slot ?? null);

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
      const profileOffer =
        offerSource === "profile"
          ? (profile?.service_description ?? profile?.profession ?? "").trim()
          : "";
      const customOffer = offerSource === "custom" ? profession.trim() : "";
      const offerText = offerSource === "profile" ? profileOffer : customOffer;
      const offerParts = [
        offerText || null,
        idealCustomer
          ? `${t("search.form.ideal")}: ${idealCustomer}`
          : null,
        exclusions ? `${t("search.form.exclude")}: ${exclusions}` : null,
      ].filter(Boolean);
      const resp = await createSearch({
        niche,
        region,
        profession: offerParts.join(". ") || undefined,
        target_languages:
          targetLanguages.length > 0 ? targetLanguages : undefined,
        team_id: activeTeamId(),
        limit: leadLimit,
        scope,
        radius_km: scope === "city" || scope === "metro" ? radiusKm : undefined,
      });
      router.push(`/app/sessions/${resp.id}`);
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : String(e));
      setLaunching(false);
    }
  };

  const launchDisabled =
    launching ||
    !niche.trim() ||
    !region.trim() ||
    duplicateMatches.length > 0;

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
          onSubmit={() => sendToHenry(draft)}
          chatRef={chatRef}
        />

        <FormColumn
          niche={niche}
          region={region}
          idealCustomer={idealCustomer}
          exclusions={exclusions}
          profession={profession}
          targetLanguages={targetLanguages}
          aiTouched={aiTouched}
          profile={profile}
          offerSource={offerSource}
          onOfferSourceChange={setOfferSource}
          onNicheChange={(v) => setNiche(v)}
          onRegionChange={(v) => setRegion(v)}
          onIdealCustomerChange={(v) => setIdealCustomer(v)}
          onExclusionsChange={(v) => setExclusions(v)}
          onProfessionChange={(v) => setProfession(v)}
          onTargetLanguagesChange={setTargetLanguages}
          leadLimit={leadLimit}
          onLeadLimitChange={setLeadLimit}
          scope={scope}
          onScopeChange={setScope}
          radiusKm={radiusKm}
          onRadiusKmChange={setRadiusKm}
          readyHint={readyToLaunch}
          onLaunch={launch}
          launching={launching}
          launchDisabled={launchDisabled}
          submitError={submitError}
          duplicateMatches={duplicateMatches}
          axesOptions={axesOptions}
          axesLoading={axesLoading}
          axesError={axesError}
          onFetchAxes={fetchAxes}
          onApplyAxis={applyAxis}
          onDismissAxes={() => setAxesOptions(null)}
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
  chatRef,
}: {
  messages: ChatMsg[];
  thinking: boolean;
  draft: string;
  onDraftChange: (v: string) => void;
  onSubmit: () => void;
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
        <HenryAvatar size={40} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 14, fontWeight: 700 }}>Henry</div>
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
        <HenryAvatar size={28} />
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
      <HenryAvatar size={28} />
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

const LANGUAGE_OPTIONS = [
  { code: "ru", labelKey: "search.lang.ru" as const },
  { code: "uk", labelKey: "search.lang.uk" as const },
  { code: "en", labelKey: "search.lang.en" as const },
  { code: "de", labelKey: "search.lang.de" as const },
  { code: "es", labelKey: "search.lang.es" as const },
  { code: "fr", labelKey: "search.lang.fr" as const },
  { code: "pl", labelKey: "search.lang.pl" as const },
];

function FormColumn({
  niche,
  region,
  idealCustomer,
  exclusions,
  profession,
  targetLanguages,
  aiTouched,
  profile,
  offerSource,
  onOfferSourceChange,
  onNicheChange,
  onRegionChange,
  onIdealCustomerChange,
  onExclusionsChange,
  onProfessionChange,
  onTargetLanguagesChange,
  leadLimit,
  onLeadLimitChange,
  scope,
  onScopeChange,
  radiusKm,
  onRadiusKmChange,
  readyHint,
  onLaunch,
  launching,
  launchDisabled,
  submitError,
  duplicateMatches,
  axesOptions,
  axesLoading,
  axesError,
  onFetchAxes,
  onApplyAxis,
  onDismissAxes,
}: {
  niche: string;
  region: string;
  idealCustomer: string;
  exclusions: string;
  profession: string;
  targetLanguages: string[];
  aiTouched: Record<string, number>;
  profile: UserProfile | null;
  offerSource: OfferSource;
  onOfferSourceChange: (v: OfferSource) => void;
  onNicheChange: (v: string) => void;
  onRegionChange: (v: string) => void;
  onIdealCustomerChange: (v: string) => void;
  onExclusionsChange: (v: string) => void;
  onProfessionChange: (v: string) => void;
  onTargetLanguagesChange: (v: string[]) => void;
  leadLimit: LeadLimitChoice;
  onLeadLimitChange: (v: LeadLimitChoice) => void;
  scope: SearchScope;
  onScopeChange: (v: SearchScope) => void;
  radiusKm: RadiusChoiceKm;
  onRadiusKmChange: (v: RadiusChoiceKm) => void;
  readyHint: boolean;
  onLaunch: () => void;
  launching: boolean;
  launchDisabled: boolean;
  submitError: string | null;
  duplicateMatches: PriorTeamSearch[];
  axesOptions: SearchAxisOption[] | null;
  axesLoading: boolean;
  axesError: string | null;
  onFetchAxes: () => void;
  onApplyAxis: (opt: SearchAxisOption) => void;
  onDismissAxes: () => void;
}) {
  const { t } = useLocale();

  const profileOffer =
    (profile?.service_description?.trim() ||
      profile?.profession?.trim() ||
      "") ?? "";
  const profileHasOffer = profileOffer.length > 0;

  const filledCount = useMemo(() => {
    let n = 0;
    if (niche.trim()) n++;
    if (region.trim()) n++;
    if (idealCustomer.trim()) n++;
    if (exclusions.trim()) n++;
    if (targetLanguages.length > 0) n++;
    const offerFilled =
      offerSource === "profile" ? profileHasOffer : profession.trim().length > 0;
    if (offerFilled) n++;
    return n;
  }, [
    niche,
    region,
    idealCustomer,
    exclusions,
    targetLanguages,
    profession,
    offerSource,
    profileHasOffer,
  ]);

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
            · {filledCount}/6
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

      <SuggestAxesPanel
        profile={profile}
        loading={axesLoading}
        options={axesOptions}
        error={axesError}
        onFetch={onFetchAxes}
        onApply={onApplyAxis}
        onDismiss={onDismissAxes}
      />

      <FormCard
        icon="folder"
        label={t("search.form.niche")}
        hint={t("search.form.nicheHint")}
        required
        flashKey={aiTouched.niche}
      >
        <NicheCombobox
          value={niche}
          onChange={onNicheChange}
          placeholder={t("search.form.nichePh")}
          language={profile?.language_code ?? undefined}
        />
      </FormCard>

      <FormCard
        icon="mapPin"
        label={t("search.form.region")}
        hint={t("search.form.regionHint")}
        required
        flashKey={aiTouched.region}
      >
        <RegionCombobox
          value={region}
          onChange={onRegionChange}
          placeholder={t("search.form.regionPh")}
          language={profile?.language_code ?? undefined}
        />
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
          {SEARCH_SCOPES.map((s) => {
            const active = scope === s;
            const labels: Record<SearchScope, string> = {
              city: "Город",
              metro: "Метро + радиус",
              state: "Штат / область",
              country: "Страна",
            };
            return (
              <button
                key={s}
                type="button"
                onClick={() => onScopeChange(s)}
                style={{
                  padding: "5px 11px",
                  fontSize: 12,
                  borderRadius: 999,
                  cursor: "pointer",
                  border: active
                    ? "1px solid var(--accent)"
                    : "1px solid var(--border)",
                  background: active
                    ? "color-mix(in srgb, var(--accent) 14%, transparent)"
                    : "var(--surface-2)",
                  color: active ? "var(--accent)" : "var(--text)",
                  fontWeight: active ? 600 : 500,
                }}
              >
                {labels[s]}
              </button>
            );
          })}
        </div>
        {(scope === "city" || scope === "metro") && (
          <div style={{ marginTop: 10 }}>
            <div
              className="eyebrow"
              style={{ fontSize: 10, marginBottom: 6 }}
            >
              Радиус: {radiusKm} км
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {RADIUS_CHOICES_KM.map((r) => {
                const active = radiusKm === r;
                return (
                  <button
                    key={r}
                    type="button"
                    onClick={() => onRadiusKmChange(r)}
                    style={{
                      padding: "4px 10px",
                      fontSize: 12,
                      borderRadius: 999,
                      cursor: "pointer",
                      border: active
                        ? "1px solid var(--accent)"
                        : "1px solid var(--border)",
                      background: active
                        ? "color-mix(in srgb, var(--accent) 14%, transparent)"
                        : "var(--surface-2)",
                      color: active ? "var(--accent)" : "var(--text)",
                      fontWeight: active ? 600 : 500,
                      minWidth: 44,
                    }}
                  >
                    {r}&nbsp;км
                  </button>
                );
              })}
            </div>
          </div>
        )}
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
        icon="globe"
        label={t("search.form.lang")}
        hint={t("search.form.langHint")}
      >
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {LANGUAGE_OPTIONS.map((opt) => {
            const active = targetLanguages.includes(opt.code);
            return (
              <button
                key={opt.code}
                type="button"
                onClick={() => {
                  onTargetLanguagesChange(
                    active
                      ? targetLanguages.filter((c) => c !== opt.code)
                      : [...targetLanguages, opt.code],
                  );
                }}
                style={{
                  padding: "6px 12px",
                  fontSize: 12.5,
                  borderRadius: 999,
                  cursor: "pointer",
                  border: active
                    ? "1px solid var(--accent)"
                    : "1px solid var(--border)",
                  background: active
                    ? "color-mix(in srgb, var(--accent) 14%, transparent)"
                    : "var(--surface-2)",
                  color: active ? "var(--accent)" : "var(--text)",
                  fontWeight: active ? 600 : 500,
                }}
              >
                {t(opt.labelKey)}
              </button>
            );
          })}
        </div>
        <div
          style={{
            fontSize: 11.5,
            color: "var(--text-dim)",
            marginTop: 8,
            lineHeight: 1.45,
          }}
        >
          {t("search.form.langHelp")}
        </div>
      </FormCard>

      <FormCard
        icon="filter"
        label="Сколько лидов искать"
        hint="Чем меньше — тем быстрее и дешевле по AI-кредитам"
      >
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {LEAD_LIMIT_CHOICES.map((n) => {
            const active = leadLimit === n;
            return (
              <button
                key={n}
                type="button"
                onClick={() => onLeadLimitChange(n)}
                style={{
                  padding: "6px 14px",
                  fontSize: 13,
                  borderRadius: 999,
                  cursor: "pointer",
                  border: active
                    ? "1px solid var(--accent)"
                    : "1px solid var(--border)",
                  background: active
                    ? "color-mix(in srgb, var(--accent) 14%, transparent)"
                    : "var(--surface-2)",
                  color: active ? "var(--accent)" : "var(--text)",
                  fontWeight: active ? 600 : 500,
                  minWidth: 44,
                }}
              >
                {n}
              </button>
            );
          })}
        </div>
        <div
          style={{
            fontSize: 11.5,
            color: "var(--text-dim)",
            marginTop: 8,
            lineHeight: 1.45,
          }}
        >
          Источники: Google Places + OpenStreetMap (если ниша
          совпадает с таксономией). OSM хорошо покрывает EU/UA/UK
          и работает бесплатно.
        </div>
      </FormCard>

      <FormCard
        icon="briefcase"
        label={t("search.form.offer")}
        hint={t("search.form.offerHint")}
      >
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <SourceTab
            label={t("search.form.offerSource.profile")}
            active={offerSource === "profile"}
            disabled={!profileHasOffer}
            onClick={() => onOfferSourceChange("profile")}
          />
          <SourceTab
            label={t("search.form.offerSource.custom")}
            active={offerSource === "custom"}
            onClick={() => onOfferSourceChange("custom")}
          />
        </div>
        {offerSource === "profile" ? (
          profileHasOffer ? (
            <div
              style={{
                marginTop: 4,
                padding: "11px 13px",
                borderRadius: 10,
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                fontSize: 13,
                lineHeight: 1.55,
                color: "var(--text)",
                whiteSpace: "pre-wrap",
              }}
            >
              {profileOffer}
            </div>
          ) : (
            <div
              style={{
                marginTop: 4,
                fontSize: 12.5,
                color: "var(--text-muted)",
                lineHeight: 1.5,
              }}
            >
              {t("search.form.offerSource.profileEmpty")}{" "}
              <Link
                href="/app/profile"
                style={{ color: "var(--accent)", fontWeight: 600 }}
              >
                {t("search.form.offerSource.profileLink")}
              </Link>
            </div>
          )
        ) : (
          <>
            <textarea
              className="textarea"
              rows={3}
              value={profession}
              onChange={(e) => onProfessionChange(e.target.value)}
              placeholder={t("search.form.offerPh")}
            />
            {!profileHasOffer && (
              <div
                style={{
                  fontSize: 11.5,
                  color: "var(--text-dim)",
                  lineHeight: 1.45,
                }}
              >
                {t("search.form.offerSource.empty")}
              </div>
            )}
          </>
        )}
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

      {duplicateMatches.length > 0 && (
        <div
          style={{
            padding: "14px 16px",
            border:
              "1px solid color-mix(in srgb, var(--cold) 35%, var(--border))",
            background: "color-mix(in srgb, var(--cold) 6%, var(--surface))",
            borderRadius: 12,
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              color: "var(--cold)",
              fontSize: 13,
              fontWeight: 600,
            }}
          >
            <Icon name="x" size={14} />
            {t("search.preflight.title")}
          </div>
          <div
            style={{
              fontSize: 12.5,
              color: "var(--text-muted)",
              lineHeight: 1.5,
            }}
          >
            {t("search.preflight.body")}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {duplicateMatches.slice(0, 3).map((m) => (
              <div
                key={m.search_id}
                style={{
                  fontSize: 12,
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  color: "var(--text)",
                }}
              >
                <span style={{ fontWeight: 600 }}>{m.user_name}</span>
                <span style={{ color: "var(--text-dim)" }}>·</span>
                <span style={{ color: "var(--text-muted)" }}>
                  {new Date(m.created_at).toLocaleDateString()}
                </span>
                <span style={{ color: "var(--text-dim)" }}>·</span>
                <span style={{ color: "var(--text-muted)" }}>
                  {t("search.preflight.leadsCount", { n: m.leads_count })}
                </span>
                <Link
                  href={`/app/sessions/${m.search_id}`}
                  style={{
                    marginLeft: "auto",
                    color: "var(--accent)",
                    fontSize: 11.5,
                  }}
                >
                  {t("search.preflight.openSession")}
                </Link>
              </div>
            ))}
          </div>
        </div>
      )}

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

function SourceTab({
  label,
  active,
  disabled,
  onClick,
}: {
  label: string;
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: "7px 13px",
        fontSize: 12.5,
        fontWeight: active ? 600 : 500,
        borderRadius: 999,
        cursor: disabled ? "not-allowed" : "pointer",
        border: active
          ? "1px solid var(--accent)"
          : "1px solid var(--border)",
        background: active
          ? "color-mix(in srgb, var(--accent) 14%, transparent)"
          : "var(--surface-2)",
        color: disabled
          ? "var(--text-dim)"
          : active
            ? "var(--accent)"
            : "var(--text)",
        opacity: disabled ? 0.6 : 1,
      }}
    >
      {label}
    </button>
  );
}

function SuggestAxesPanel({
  profile,
  loading,
  options,
  error,
  onFetch,
  onApply,
  onDismiss,
}: {
  profile: UserProfile | null;
  loading: boolean;
  options: SearchAxisOption[] | null;
  error: string | null;
  onFetch: () => void;
  onApply: (opt: SearchAxisOption) => void;
  onDismiss: () => void;
}) {
  const { t } = useLocale();

  // Auto-fill is only meaningful when Henry has SOMETHING to base
  // suggestions on. Without a profile signal we'd just be calling
  // the LLM with an empty seed.
  const profileHasSignal = Boolean(
    (profile?.service_description ?? "").trim() ||
      (profile?.profession ?? "").trim() ||
      (profile?.niches ?? []).length > 0 ||
      (profile?.home_region ?? "").trim(),
  );
  if (!profileHasSignal) return null;

  return (
    <div
      style={{
        padding: 14,
        borderRadius: 12,
        border:
          "1px solid color-mix(in srgb, var(--accent) 25%, var(--border))",
        background:
          "linear-gradient(135deg, color-mix(in srgb, var(--accent) 8%, var(--surface)), var(--surface))",
        display: "flex",
        flexDirection: "column",
        gap: 10,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 10,
        }}
      >
        <div>
          <div className="eyebrow" style={{ marginBottom: 2 }}>
            {t("search.axes.eyebrow")}
          </div>
          <div
            style={{
              fontSize: 13,
              color: "var(--text-muted)",
              lineHeight: 1.5,
            }}
          >
            {t("search.axes.subtitle")}
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
          {options !== null && (
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              onClick={onDismiss}
              disabled={loading}
            >
              {t("search.axes.hide")}
            </button>
          )}
          <button
            type="button"
            className="btn btn-sm"
            onClick={onFetch}
            disabled={loading}
          >
            <Icon name="sparkles" size={13} />
            {loading
              ? t("common.loading")
              : options === null
                ? t("search.axes.cta")
                : t("search.axes.ctaAgain")}
          </button>
        </div>
      </div>

      {error && (
        <div style={{ fontSize: 12, color: "var(--cold)" }}>{error}</div>
      )}

      {options !== null && options.length === 0 && !loading && (
        <div
          style={{ fontSize: 12, color: "var(--text-dim)", lineHeight: 1.5 }}
        >
          {t("search.axes.empty")}
        </div>
      )}

      {options !== null && options.length > 0 && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 8,
          }}
        >
          {options.map((opt, i) => (
            <button
              key={i}
              type="button"
              onClick={() => onApply(opt)}
              style={{
                textAlign: "left",
                padding: 12,
                background: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: 10,
                cursor: "pointer",
                display: "flex",
                flexDirection: "column",
                gap: 4,
              }}
            >
              <div
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  letterSpacing: "-0.005em",
                }}
              >
                {opt.niche}
              </div>
              <div
                style={{
                  fontSize: 12,
                  color: "var(--text-muted)",
                }}
              >
                {opt.region}
              </div>
              {opt.rationale && (
                <div
                  style={{
                    fontSize: 11.5,
                    color: "var(--text-dim)",
                    lineHeight: 1.4,
                    marginTop: 4,
                  }}
                >
                  {opt.rationale}
                </div>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
