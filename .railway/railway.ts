import { defineRailway, postgres, preserve, project, redis, service, volume } from "railway/iac";

export default defineRailway(() => {
  const Postgres = postgres("Postgres", { region: "sfo" });
  const Redis = redis("Redis", { region: "sfo" });
  Redis.deploy = { startCommand: "/bin/sh -c \"rm -rf $RAILWAY_VOLUME_MOUNT_PATH/lost+found/ && exec docker-entrypoint.sh redis-server --requirepass $REDIS_PASSWORD --save 60 1 --dir $RAILWAY_VOLUME_MOUNT_PATH\"" };
  const postgresVolume = volume("postgres-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "sfo", sizeMB: 500 });
  const redisVolume = volume("redis-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "sfo", sizeMB: 500 });
  const api = service("api", {
    replicas: { "sfo": 1 },
    env: { AUTH_JWT_SECRET: preserve(), BILLING_ENFORCED: preserve(), DATABASE_URL: preserve(), DEMO_MODE: preserve(), FERNET_KEY: preserve(), REDIS_URL: preserve() },
  });
  // Тот же образ, что и api, но запускается воркером очереди.
  //
  // Railway при заданном startCommand обходит ENTRYPOINT образа, то
  // есть entrypoint.sh здесь не выполняется и миграции не запускаются
  // сами по себе. RUN_MIGRATIONS=0 оставлен страховкой: он сработает,
  // если образ поднимут штатным способом (docker run, другая
  // платформа), где entrypoint отработает и полезет в alembic
  // одновременно с api.
  const workeer = service("workeer", {
    replicas: { "sfo": 1 },
    deploy: { startCommand: "arq leadgen.queue.worker.WorkerSettings" },
    env: {
      AUTH_JWT_SECRET: preserve(),
      DATABASE_URL: preserve(),
      DEMO_MODE: preserve(),
      FERNET_KEY: preserve(),
      REDIS_URL: preserve(),
      RUN_MIGRATIONS: preserve(),
    },
  });

  return project("charming-victory", {
    resources: [Postgres, api, Redis, workeer, postgresVolume, redisVolume],
  });
});
