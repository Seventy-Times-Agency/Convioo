"use client";

import { SectionTabs } from "@/components/layout/SectionTabs";
import {
  Suspense,
  useEffect,
  useRef,
  useState,
} from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Topbar } from "@/components/layout/Topbar";
import { ChatColumn } from "@/components/search/ChatColumn";
import {
  EXCLUSION_PRESETS,
  SearchComposer,
  type CityPick,
  type CityRadiusKm,
  type WebsiteFilter,
} from "@/components/search/SearchComposer";
import { Icon } from "@/components/brand/Icon";
import type { ChatMsg, OfferSource } from "@/components/search/types";
import {
  ApiError,
  DEFAULT_LEAD_LIMIT,
  consultSearch,
  createSavedSearch,
  createSearch,
  getSearchChannels,
  getMyProfile,
  getTeamUsage,
  preflightSearch,
  suggestSearchAxes,
  type ConsultSlot,
  type LeadLimitChoice,
  type PriorTeamSearch,
  type SearchForecast,
  type SearchAxisOption,
  type UserProfile,
  type SearchChannel,
} from "@/lib/api";
import { activeTeamId, subscribeWorkspace } from "@/lib/workspace";
import { useLocale } from "@/lib/i18n";
import { useIsMobile } from "@/lib/hooks/useMediaQuery";

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
  const isMobile = useIsMobile();

  const [niche, setNiche] = useState(searchParams.get("niche") ?? "");
  // Города: список с радиусом у каждого; каждый город — своя сессия.
  // ``regionDraft`` — то, что сейчас набрано в поле добавления.
  const [cities, setCities] = useState<CityPick[]>(() => {
    const r = searchParams.get("region");
    return r ? [{ name: r, country: null, population: null, radiusKm: 0 }] : [];
  });
  const [regionDraft, setRegionDraft] = useState("");
  const addCity = (c: CityPick) => {
    setCities((prev) =>
      prev.some((x) => x.name.toLowerCase() === c.name.toLowerCase())
        ? prev
        : [...prev, c],
    );
    setRegionDraft("");
  };
  const removeCity = (name: string) =>
    setCities((prev) => prev.filter((c) => c.name !== name));
  const setCityRadius = (name: string, r: CityRadiusKm) =>
    setCities((prev) => prev.map((c) => (c.name === name ? { ...c, radiusKm: r } : c)));
  // Henry и подсказки работают с «регионом» как со строкой — это
  // первый город списка.
  const region = cities[0]?.name ?? "";
  const setRegion = (v: string) => {
    if (!v.trim()) return;
    setCities((prev) =>
      prev.length === 0
        ? [{ name: v, country: null, population: null, radiusKm: 0 }]
        : [{ ...prev[0], name: v, country: null, population: null }, ...prev.slice(1)],
    );
  };
  const [idealCustomer, setIdealCustomer] = useState("");
  const [exclusions, setExclusions] = useState("");
  const [exclusionPresets, setExclusionPresets] = useState<Set<string>>(new Set());
  const [profession, setProfession] = useState("");
  const [targetLanguages, setTargetLanguages] = useState<string[]>([]);
  const [leadLimit, setLeadLimit] = useState<LeadLimitChoice>(DEFAULT_LEAD_LIMIT);
  const [websiteFilter, setWebsiteFilter] = useState<WebsiteFilter>("any");
  const [minRating, setMinRating] = useState(0);
  const [minReviews, setMinReviews] = useState(0);
  const [repeatWeekly, setRepeatWeekly] = useState(false);
  const [tokensBalance, setTokensBalance] = useState<number | null>(null);
  // Henry живёт в выдвижной панели: постоянная колонка чата съедала
  // половину экрана и утапливала настройку вниз.
  const [henryOpen, setHenryOpen] = useState(false);
  const [channels, setChannels] = useState<SearchChannel[]>([]);
  const [selectedChannels, setSelectedChannels] = useState<Set<string>>(
    new Set(),
  );
  // Выключен по умолчанию: платная операция включается осознанно.
  const [findDecisionMakers, setFindDecisionMakers] = useState(false);

  // Profile drives the "use my profile / custom" offer toggle. Loaded
  // once on mount; when present, that's the default source so the user
  // doesn't retype what's already on file.
  const [profile, setProfile] = useState<UserProfile | null>(null);

  // Описания каналов живут на сервере — форма их не выдумывает.
  useEffect(() => {
    getSearchChannels()
      .then((list) => {
        setChannels(list);
        setSelectedChannels(new Set(list.map((c) => c.key)));
      })
      .catch(() => undefined);
  }, []);
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
  const [duplicates, setDuplicates] = useState<Record<string, PriorTeamSearch[]>>({});
  // Прогноз по каждому городу и подтверждения «добрать новых» там,
  // где команда уже искала эту нишу.
  const [forecasts, setForecasts] = useState<Record<string, SearchForecast>>({});
  const [acknowledged, setAcknowledged] = useState<Set<string>>(new Set());
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

  // Состояние, а не чтение при рендере: после смены пространства
  // история и предпросчёт иначе оставались от старой команды.
  const [teamId, setTeamId] = useState<string | undefined>(() => activeTeamId());
  useEffect(
    () => subscribeWorkspace(() => setTeamId(activeTeamId())),
    [],
  );

  useEffect(() => {
    if (!teamId) {
      setTokensBalance(null);
      return;
    }
    let cancelled = false;
    getTeamUsage(teamId)
      .then((u) => !cancelled && setTokensBalance(u.token_balance))
      .catch(() => !cancelled && setTokensBalance(null));
    return () => {
      cancelled = true;
    };
  }, [teamId]);

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

  // Повтор той же ниши и города в команде — не запрет, а «добрать
  // новых»: запуск идёт в нетронутые районы и формулировки. Прогноз
  // (сколько уже получено, сколько свежих ждать) — по каждому городу.
  const cityKey = cities.map((c) => c.name).join("|");
  useEffect(() => {
    setAcknowledged(new Set());
  }, [niche, teamId]);
  useEffect(() => {
    if (!niche.trim() || cities.length === 0) {
      setDuplicates({});
      setForecasts({});
      return;
    }
    let cancelled = false;
    const handle = window.setTimeout(() => {
      Promise.all(
        cities.map((c) =>
          preflightSearch({ niche, region: c.name, teamId, limit: leadLimit })
            .then((r): [string, PriorTeamSearch[], SearchForecast | null] => [c.name, r.matches, r.forecast])
            .catch((): [string, PriorTeamSearch[], SearchForecast | null] => [c.name, [], null]),
        ),
      ).then((rows) => {
        if (cancelled) return;
        const dups: Record<string, PriorTeamSearch[]> = {};
        const fcs: Record<string, SearchForecast> = {};
        for (const [name, m, fc] of rows) {
          if (m.length) dups[name] = m;
          if (fc) fcs[name] = fc;
        }
        setDuplicates(dups);
        setForecasts(fcs);
      });
    }, 350);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [teamId, niche, cityKey, leadLimit]);


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
    if (!niche || cities.length === 0) return;
    setSubmitError(null);
    setLaunching(true);
    try {
      const profileOffer =
        offerSource === "profile"
          ? (profile?.service_description ?? profile?.profession ?? "").trim()
          : "";
      const customOffer = offerSource === "custom" ? profession.trim() : "";
      const offerText = offerSource === "profile" ? profileOffer : customOffer;
      const presetText = EXCLUSION_PRESETS.filter((e) => exclusionPresets.has(e.key))
        .map((e) => t(e.labelKey))
        .join(", ");
      const exclusionText = [presetText, exclusions.trim()].filter(Boolean).join(", ");
      const offerParts = [
        offerText || null,
        idealCustomer ? `${t("search.form.ideal")}: ${idealCustomer}` : null,
      ].filter(Boolean);
      const channelsArg =
        channels.length > 0 && selectedChannels.size < channels.length
          ? Array.from(selectedChannels)
          : undefined;
      // Каждый город — отдельная сессия; запускаем по очереди, чтобы
      // сервер поставил их в очередь в том порядке, что на экране.
      let firstId: string | null = null;
      for (const c of cities) {
        const resp = await createSearch({
          niche,
          region: c.name,
          country_code: c.country ?? undefined,
          profession: offerParts.join(". ") || undefined,
          exclusions: exclusionText || undefined,
          target_languages: targetLanguages.length > 0 ? targetLanguages : undefined,
          team_id: teamId,
          limit: leadLimit,
          scope: c.radiusKm ? "metro" : "city",
          radius_km: c.radiusKm || undefined,
          channels: channelsArg,
          find_decision_makers: findDecisionMakers,
          allow_repeat: acknowledged.has(c.name) || undefined,
          website_filter: websiteFilter === "any" ? undefined : websiteFilter,
          min_rating: minRating || undefined,
          min_reviews: minReviews || undefined,
        });
        firstId = firstId ?? resp.id;
        if (repeatWeekly) {
          // Еженедельный повтор — сохранённый поиск с расписанием;
          // сбой тут не должен ронять уже запущенный сбор.
          try {
            await createSavedSearch({
              name: `${niche} · ${c.name}`,
              niche,
              region: c.name,
              scope: c.radiusKm ? "metro" : "city",
              radius_m: c.radiusKm ? c.radiusKm * 1000 : null,
              max_results: Math.min(leadLimit, 100),
              schedule: "weekly",
              team_id: teamId ?? null,
              target_languages: targetLanguages.length > 0 ? targetLanguages : undefined,
              launch_params: {
                country_code: c.country ?? undefined,
                profession: offerParts.join(". ") || undefined,
                exclusions: exclusionText || undefined,
                channels: channelsArg,
                find_decision_makers: findDecisionMakers,
                website_filter: websiteFilter === "any" ? undefined : websiteFilter,
                min_rating: minRating || undefined,
                min_reviews: minReviews || undefined,
              },
            });
          } catch {
            // ignore — основной запуск уже ушёл
          }
        }
      }
      if (firstId) router.push(`/app/sessions/${firstId}`);
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : String(e));
      setLaunching(false);
    }
  };

  const launchDisabled =
    launching ||
    !niche.trim() ||
    cities.length === 0 ||
    Object.keys(duplicates).some((name) => !acknowledged.has(name));

  return (
    <>
      <Topbar
        crumbs={[
          { label: t("search.crumb.workspace"), href: "/app" },
          { label: t("search.crumb.new") },
        ]}
        right={
          <div style={{ display: "flex", gap: 8 }}>
            <button
              className="btn btn-ghost btn-sm"
              onClick={fetchAxes}
              type="button"
              style={{ color: "var(--accent)" }}
              title={t("search.axes.subtitle")}
            >
              <Icon name="sparkles" size={13} /> {t("search.axes.eyebrow")}
            </button>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setHenryOpen(true)}
              type="button"
            >
              <Icon name="chat" size={13} /> Henry
            </button>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => router.push("/app")}
              type="button"
            >
              {t("common.cancel")}
            </button>
          </div>
        }
      />
      <div className="page" style={{ maxWidth: 1240 }}>
        <SectionTabs section="dobycha" />
        <SearchComposer
          niche={niche}
          onNicheChange={setNiche}
          idealCustomer={idealCustomer}
          onIdealCustomerChange={setIdealCustomer}
          exclusions={exclusions}
          onExclusionsChange={setExclusions}
          exclusionPresets={exclusionPresets}
          onToggleExclusionPreset={(key) =>
            setExclusionPresets((prev) => {
              const next = new Set(prev);
              if (next.has(key)) next.delete(key);
              else next.add(key);
              return next;
            })
          }
          targetLanguages={targetLanguages}
          onTargetLanguagesChange={setTargetLanguages}
          aiTouched={aiTouched}
          regionDraft={regionDraft}
          onRegionDraftChange={setRegionDraft}
          cities={cities}
          onAddCity={addCity}
          onRemoveCity={removeCity}
          onCityRadius={setCityRadius}
          leadLimit={leadLimit}
          onLeadLimitChange={setLeadLimit}
          channels={channels}
          selectedChannels={selectedChannels}
          onToggleChannel={(key) =>
            setSelectedChannels((prev) => {
              const next = new Set(prev);
              // Если выбрано «везде» — клик по каналу оставляет только его
              // (плюс обязательные).
              if (next.size === channels.length) {
                const required = channels.filter((c) => c.required).map((c) => c.key);
                return new Set([...required, key]);
              }
              if (next.has(key)) {
                if (channels.find((c) => c.key === key)?.required) return prev;
                next.delete(key);
              } else next.add(key);
              return next;
            })
          }
          onAllChannels={() => setSelectedChannels(new Set(channels.map((c) => c.key)))}
          repeatWeekly={repeatWeekly}
          onToggleRepeatWeekly={() => setRepeatWeekly((v) => !v)}
          websiteFilter={websiteFilter}
          onWebsiteFilterChange={setWebsiteFilter}
          minRating={minRating}
          onMinRatingChange={setMinRating}
          minReviews={minReviews}
          onMinReviewsChange={setMinReviews}
          findDecisionMakers={findDecisionMakers}
          onToggleDecisionMakers={() => setFindDecisionMakers((v) => !v)}
          offerSource={offerSource}
          onOfferSourceChange={setOfferSource}
          profession={profession}
          onProfessionChange={setProfession}
          profile={profile}
          tokensBalance={tokensBalance}
          onLaunch={launch}
          launching={launching}
          launchDisabled={launchDisabled}
          submitError={submitError}
          duplicates={duplicates}
          forecasts={forecasts}
          acknowledged={acknowledged}
          onAcknowledge={(name) =>
            setAcknowledged((prev) => {
              const next = new Set(prev);
              if (next.has(name)) next.delete(name);
              else next.add(name);
              return next;
            })
          }
          onOpenHenry={() => setHenryOpen(true)}
          axesOptions={axesOptions}
          axesLoading={axesLoading}
          axesError={axesError}
          onFetchAxes={fetchAxes}
          onApplyAxis={applyAxis}
          onDismissAxes={() => setAxesOptions(null)}
          teamId={teamId}
          onRepeat={(n, r) => {
            setNiche(n);
            setCities([{ name: r, country: null, population: null, radiusKm: 0 }]);
            window.scrollTo({ top: 0, behavior: "smooth" });
          }}
        />
      </div>

      {henryOpen && (
        <div className="henry-drawer" role="dialog" aria-label="Henry">
          <div className="henry-drawer-head">
            <span style={{ fontWeight: 800, fontSize: 14 }}>
              {t("search.form.henryBtn")}
            </span>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setHenryOpen(false)}
              aria-label={t("common.close")}
            >
              <Icon name="x" size={15} />
            </button>
          </div>
          <div style={{ flexGrow: 1, minHeight: 0, display: "flex", flexDirection: "column", padding: "0 14px 14px" }}>
            <ChatColumn
              messages={messages}
              thinking={thinking}
              draft={draft}
              onDraftChange={setDraft}
              onSubmit={() => sendToHenry(draft)}
              chatRef={chatRef}
            />
          </div>
        </div>
      )}
    </>
  );
}
