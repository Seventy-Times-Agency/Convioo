"use client";

export default function SettingsNotificationsPage() {
  return (
    <div className="card" style={{ padding: 24, marginBottom: 14 }}>
      <div className="eyebrow" style={{ marginBottom: 14 }}>
        Уведомления
      </div>
      <div
        style={{
          fontSize: 13.5,
          color: "var(--text-muted)",
          lineHeight: 1.55,
        }}
      >
        Транзакционные письма (верификация email, восстановление пароля,
        вход с нового устройства) приходят автоматически. Дайджесты по
        новым лидам и weekly check-in от Henry — в разработке.
      </div>
    </div>
  );
}
