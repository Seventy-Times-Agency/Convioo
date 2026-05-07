"use client";

import {
  Suspense,
  useEffect,
  useRef,
  useState,
} from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Topbar } from "@/components/layout/Topbar";
import { ChatColumn } from "@/components/search/ChatColumn";
import { FormColumn } from "@/components/search/FormColumn";
import type { ChatMsg, OfferSource } from "@/components/search/types";
import {
  ApiError,
  DEFAULT_LEAD_LIMIT,
  SEARCH_SOURCES,
  consultSearch,
  createSearch,
  getMyProfile,
  preflightSearch,
  suggestSearchAxes,
  type ConsultSlot,
  type LeadLimitChoice,
  type PriorTeamSearch,
  type RadiusChoiceKm,
  type SearchAxisOption,
  type SearchScope,
  type SearchSource,
  type UserProfile,
} from "@/lib/api";
import { activeTeamId } from "@/lib/workspace";
import { useLocale } from "@/lib/i18n";

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
  // Source toggles (T6) — all on by default; user can opt out of a
  // hot-rate-limited source for this run only. Persisted to
  // localStorage so the toggle stays sticky across navigations.
  const [enabledSources, setEnabledSources] = useState<Set<SearchSource>>(
    () => new Set(SEARCH_SOURCES),
  );

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
      // ``enabled_sources`` is sent only when the user actually opted
      // out of at least one — otherwise we let the server's defaults
      // win so we don't hard-pin choices that get added later.
      const sourcesArr = Array.from(enabledSources);
      const sourcesOverride =
        sourcesArr.length === SEARCH_SOURCES.length
          ? undefined
          : sourcesArr;
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
        enabled_sources: sourcesOverride,
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
          enabledSources={enabledSources}
          onToggleSource={(src) =>
            setEnabledSources((prev) => {
              const next = new Set(prev);
              if (next.has(src)) {
                // Don't let the user disable the very last source —
                // an all-off search is just an error.
                if (next.size === 1) return prev;
                next.delete(src);
              } else {
                next.add(src);
              }
              return next;
            })
          }
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
