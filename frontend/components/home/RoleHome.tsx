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

/** Home.dc.html — экран селза: очередь и одна кнопка продолжения. */
function SalesHome({ data, today }: { data: TeamHome; today: string }) {
  const cb = data.next_callback_at ? new Date(data.next_callback_at) : null;
  const cbLabel = cb
    ? cb.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })
    : null;

  return (
    <div className="home-col">
      <div className="home-head">
        <h1>Главная</h1>
        <span className="scope">{today}</span>
      </div>

      <div className="home-card">
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 16,
            flexWrap: "wrap",
          }}
        >
          <div>
            <div style={{ fontSize: 17, fontWeight: 800 }}>
              {data.queue_total > 0
                ? "Очередь готова"
                : "Очередь пуста"}
            </div>
            <div
              style={{
                fontSize: 12.5,
                color: "var(--text-dim)",
                marginTop: 3,
              }}
            >
              {data.queue_total > 0 ? (
                <>
                  В очереди {data.queue_total} лидов
                  {cbLabel ? ` · первый перезвон в ${cbLabel}` : ""}
                </>
              ) : (
                "Менеджер ещё не раздал лиды в вашу воронку"
              )}
            </div>
          </div>
          {data.queue_total > 0 && (
            <Link href="/app/work" className="btn btn-primary">
              Продолжить прозвон
              <Icon name="arrow" size={15} />
            </Link>
          )}
        </div>
      </div>

      <div className="home-tiles three">
        {data.tiles.map((t) => (
          <TileCard key={t.key} label={t.label} value={t.value} hint={t.hint} />
        ))}
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
