"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/Icon";
import { getTeamHome, type TeamHome } from "@/lib/api";

/**
 * Главная — три разных экрана из docs/design/mockups:
 * OwnerHome.dc.html, MgrHome.dc.html, Home.dc.html.
 *
 * Роль возвращает сервер вместе с данными, поэтому здесь нет ни одной
 * проверки прав: селзу деньги просто не приходят.
 *
 * Числа в макетах иллюстративные — здесь всё считается из данных
 * команды. Пустая команда показывает нули, а не выдуманные значения.
 */
export function RoleHome({ teamId }: { teamId: string }) {
  const [data, setData] = useState<TeamHome | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    getTeamHome(teamId)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e?.message ?? "не удалось загрузить");
      });
    return () => {
      cancelled = true;
    };
  }, [teamId]);

  if (error) {
    return (
      <div className="home-card" role="alert">
        Не удалось загрузить главную: {error}
      </div>
    );
  }
  if (!data) {
    return (
      <div className="home-tiles">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="home-tile">
            <div className="t-label">загрузка</div>
            <div className="t-value">—</div>
          </div>
        ))}
      </div>
    );
  }

  const today = new Date().toLocaleDateString("ru-RU", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });

  if (data.role === "sales") return <SalesHome data={data} today={today} />;
  return <TeamHome_ data={data} today={today} />;
}

/** Home.dc.html — экран селза: план на сейчас и одна большая кнопка. */
function SalesHome({ data, today }: { data: TeamHome; today: string }) {
  const time = (iso: string | null) =>
    iso
      ? new Date(iso).toLocaleTimeString("ru-RU", {
          hour: "2-digit",
          minute: "2-digit",
        })
      : "";
  const cbLabel = data.next_callback_at ? time(data.next_callback_at) : null;
  const greeting = (() => {
    const h = new Date().getHours();
    if (h < 6) return "Доброй ночи";
    if (h < 12) return "Доброе утро";
    if (h < 18) return "Добрый день";
    return "Добрый вечер";
  })();

  return (
    <div className="home-col">
      <div className="home-head">
        <h1>Главная</h1>
        <span className="scope">{today}</span>
      </div>

      <div className="sales-grid">
        <div style={{ display: "flex", flexDirection: "column", gap: 14, minWidth: 0 }}>
          {/* Приветствие + продолжить прозвон */}
          <div className="home-card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 18, flexWrap: "wrap" }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: "-0.02em" }}>
                {greeting}
                {data.first_name ? `, ${data.first_name}` : ""}
              </div>
              <div style={{ fontSize: 13.5, color: "var(--text-muted)", marginTop: 5 }}>
                {data.queue_total > 0 ? (
                  <>
                    В очереди {data.queue_total} лидов
                    {cbLabel ? ` · первый перезвон в ${cbLabel}` : ""}
                  </>
                ) : (
                  "Очередь пуста — менеджер ещё не раздал лиды"
                )}
              </div>
            </div>
            {data.queue_total > 0 && (
              <Link href="/app/work" className="btn btn-primary btn-lg" style={{ flexShrink: 0 }}>
                <Icon name="zap" size={16} />
                Продолжить прозвон
              </Link>
            )}
          </div>

          {/* Счёт дня */}
          <div className="home-tiles three">
            <TileCard label="Наборы сегодня" value={String(data.dials_today)} hint="исходы записаны" />
            <TileCard label="Разговоры" value={String(data.conversations_today)} hint="кто-то снял трубку" />
            <TileCard label="Цели воронки" value={String(data.goals_today)} hint="зелёная кнопка" />
          </div>

          {/* Сейчас по плану */}
          <div className="home-card" style={{ flexGrow: 1 }}>
            <div className="eyebrow" style={{ marginBottom: 10 }}>
              Сейчас по плану
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {data.callbacks.length === 0 && data.letters_pending === 0 && (
                <div style={{ fontSize: 12.5, color: "var(--text-dim)" }}>
                  Назначенных касаний нет — очередь сама подскажет, кому звонить.
                </div>
              )}
              {data.callbacks.map((cb) => (
                <div
                  key={cb.lead_id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    gap: 12,
                    border: cb.overdue
                      ? "1.5px solid var(--warm)"
                      : "1px solid var(--border)",
                    background: cb.overdue
                      ? "color-mix(in srgb, var(--warm) 6%, transparent)"
                      : "var(--surface)",
                    borderRadius: 11,
                    padding: "11px 14px",
                  }}
                >
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: cb.overdue ? 800 : 700, fontSize: 14, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {cb.at ? `${time(cb.at)} · ` : ""}
                      Перезвон — {cb.lead_name}
                    </div>
                    {cb.hint && (
                      <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 2 }}>
                        {cb.hint}
                      </div>
                    )}
                  </div>
                  <Link
                    href="/app/work"
                    className={cb.overdue ? "btn btn-primary btn-sm" : "btn btn-ghost btn-sm"}
                    style={{ flexShrink: 0 }}
                  >
                    Открыть
                  </Link>
                </div>
              ))}
              {data.letters_pending > 0 && (
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    gap: 12,
                    border: "1px solid var(--border)",
                    borderRadius: 11,
                    padding: "11px 14px",
                  }}
                >
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontWeight: 700, fontSize: 14 }}>
                      {data.letters_pending}{" "}
                      {data.letters_pending === 1
                        ? "письмо-догрев ждёт одобрения"
                        : "письма-догрева ждут одобрения"}
                    </div>
                    <div style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 2 }}>
                      черновики по ручным шагам воронки
                    </div>
                  </div>
                  <Link href="/app/work/letters" className="btn btn-ghost btn-sm" style={{ flexShrink: 0 }}>
                    К письмам
                  </Link>
                </div>
              )}
            </div>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 14, minWidth: 0 }}>
          {/* Требует реакции */}
          <div className="home-card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
              <span className="eyebrow">Требует реакции</span>
              {data.reactions.some((r) => r.category === "interested" || r.category === "meeting_request") && (
                <span style={{ fontSize: 12, color: "var(--hot)", fontWeight: 800 }}>
                  срочное
                </span>
              )}
            </div>
            {data.reactions.length === 0 ? (
              <div style={{ fontSize: 12.5, color: "var(--text-dim)" }}>
                Новых ответов нет.
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {data.reactions.map((r) => {
                  const hot = r.category === "interested" || r.category === "meeting_request";
                  return (
                    <div
                      key={r.lead_id + r.at}
                      style={{
                        border: hot
                          ? "1.5px solid var(--accent)"
                          : "1px solid var(--border)",
                        background: hot
                          ? "color-mix(in srgb, var(--accent) 6%, transparent)"
                          : "var(--surface)",
                        borderRadius: 11,
                        padding: "11px 13px",
                        display: "flex",
                        flexDirection: "column",
                        gap: 6,
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                        <span style={{ fontWeight: 800, fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {r.lead_name}
                        </span>
                        <span style={{ fontSize: 11, color: "var(--text-dim)", flexShrink: 0 }}>
                          {new Date(r.at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}
                        </span>
                      </div>
                      {r.preview && (
                        <div style={{ fontSize: 12.5, color: "var(--text-muted)", lineHeight: 1.45, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                          «{r.preview}»
                        </div>
                      )}
                      <div>
                        <Link
                          href="/app/inbox"
                          className={hot ? "btn btn-primary btn-sm" : "btn btn-ghost btn-sm"}
                        >
                          {r.has_draft ? "Ответить — черновик готов" : "Открыть"}
                        </Link>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Лента дня */}
          <div className="home-card" style={{ flexGrow: 1 }}>
            <div className="eyebrow" style={{ marginBottom: 10 }}>
              Лента дня
            </div>
            {data.events.length === 0 ? (
              <div style={{ fontSize: 12.5, color: "var(--text-dim)" }}>
                Событий пока не было.
              </div>
            ) : (
              data.events.slice(0, 8).map((e, i) => (
                <div className="home-event" key={i}>
                  <span className="at">{e.at}</span>
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{e.text}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/** OwnerHome.dc.html и MgrHome.dc.html — одна раскладка, разные плитки. */
function TeamHome_({ data, today }: { data: TeamHome; today: string }) {
  const decisions = buildDecisions(data);
  const max = Math.max(1, ...data.weekly.map((w) => w.count));

  return (
    <div className="home-grid">
      <div className="home-col">
        <div className="home-head">
          <h1>Главная</h1>
          <span className="scope">
            {data.scope} · {today}
          </span>
          {/* Добыча доступна менеджеру и выше — селз сюда не попадает
              вовсе, поэтому кнопка живёт здесь, а не в Topbar, где
              роль ещё неизвестна. */}
          <Link
            href="/app/search"
            className="btn btn-primary"
            style={{ marginLeft: "auto" }}
          >
            <Icon name="plus" size={15} />
            Новый поиск
          </Link>
        </div>

        <div className="home-tiles">
          {data.tiles.map((t) => (
            <TileCard
              key={t.key}
              label={t.label}
              value={t.value}
              hint={t.hint}
            />
          ))}
        </div>

        <div className="home-card">
          <h2>Достигнутые цели по неделям</h2>
          <div className="home-bars">
            {data.weekly.map((w) => (
              <div className="home-bar" key={w.label}>
                <span className="n">{w.count}</span>
                <span
                  className="stem"
                  style={{ height: `${(w.count / max) * 110}px` }}
                />
                <span className="w">{w.label}</span>
              </div>
            ))}
          </div>
          <div className="home-note">
            12 недель. Цель засчитывается по зелёной кнопке в режиме
            прозвона.
          </div>
        </div>
      </div>

      <div className="home-col">
        <div className="home-card">
          <h2>
            {data.role === "owner"
              ? "Требует решения владельца"
              : "Требует внимания"}
          </h2>
          {decisions.length === 0 ? (
            <div className="home-note" style={{ marginTop: 0 }}>
              Ничего не требует вмешательства.
            </div>
          ) : (
            decisions.map((d, i) => (
              <div
                key={i}
                className={"home-decide" + (d.warn ? " warn" : "")}
              >
                <span className="txt">{d.text}</span>
                <span className="tag">{d.tag}</span>
              </div>
            ))
          )}
        </div>

        <div className="home-card">
          <h2>Команда · сегодня</h2>
          {data.members.length === 0 ? (
            <div className="home-note" style={{ marginTop: 0 }}>
              В команде пока нет менеджеров и селзов.
            </div>
          ) : (
            data.members.map((m) => (
              <div className="home-row" key={m.user_id}>
                <span className="who">{m.name}</span>
                <span className={"val" + (m.lagging ? " lag" : "")}>
                  {m.lagging
                    ? "0 · без наборов"
                    : `${m.goals} целей · ${m.dials} наборов`}
                </span>
              </div>
            ))
          )}
        </div>

        <div className="home-card">
          <h2>События команды</h2>
          {data.events.length === 0 ? (
            <div className="home-note" style={{ marginTop: 0 }}>
              Событий пока не было.
            </div>
          ) : (
            data.events.map((e, i) => (
              <div className="home-event" key={i}>
                <span className="at">{e.at}</span>
                <span>{e.text}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function TileCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <div className="home-tile">
      <div className="t-label">{label}</div>
      <div className="t-value">{value}</div>
      <div className="t-hint">{hint}</div>
    </div>
  );
}

/**
 * «Требует решения владельца» в макете — три придуманных строки.
 * Здесь они выводятся из реальных данных: показываем только то, что
 * действительно происходит, и ничего, если всё спокойно.
 */
function buildDecisions(
  data: TeamHome,
): { text: string; tag: string; warn?: boolean }[] {
  const out: { text: string; tag: string; warn?: boolean }[] = [];

  const cost = data.tiles.find((t) => t.key === "cost");
  if (cost && /потолок \$/.test(cost.hint)) {
    const spent = parseFloat(cost.value.replace(/[^0-9.]/g, "")) || 0;
    const cap =
      parseFloat(cost.hint.replace(/.*потолок \$/, "").replace(/\s/g, "")) || 0;
    if (cap > 0 && spent / cap >= 0.8) {
      out.push({
        text: `Затраты платформы достигли ${Math.round(
          (spent / cap) * 100,
        )}% месячного потолка`,
        tag: "поднять потолок",
        warn: true,
      });
    }
  }

  if (data.free_leads > 0) {
    out.push({
      text: `Свободных лидов: ${data.free_leads} — никто их не ведёт`,
      tag: "раздать",
    });
  }

  const idle = data.members.filter((m) => m.lagging);
  if (idle.length > 0) {
    out.push({
      text:
        idle.length === 1
          ? `${idle[0].name} сегодня без единого набора`
          : `${idle.length} человека сегодня без наборов`,
      tag: "проверить",
      warn: true,
    });
  }

  return out;
}
