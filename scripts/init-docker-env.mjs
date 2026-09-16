import { randomBytes } from 'node:crypto';
import { appendFile, readFile, writeFile } from 'node:fs/promises';

const template = await readFile(new URL('../.env.docker.example', import.meta.url), 'utf8');
const content = template.replace(
  /^(POSTGRES_PASSWORD|METIQUO_API_PASSWORD|METIQUO_WORKER_PASSWORD|METIQUO_AUTH_SECRET|PGADMIN_DEFAULT_PASSWORD)=\r?$/gm,
  (_, key) => `${key}=${randomBytes(32).toString('hex')}`,
);
try {
  await writeFile(new URL('../.env.docker', import.meta.url), content, { flag: 'wx', mode: 0o600 });
  console.log('.env.docker created with distinct database/pgAdmin passwords and an auth secret.');
} catch (error) {
  if (error.code !== 'EEXIST') throw error;
  const path = new URL('../.env.docker', import.meta.url);
  const existing = await readFile(path, 'utf8');
  const additions = [];
  const defaults = {
    METIQUO_AUTH_SECRET: () => randomBytes(32).toString('hex'),
    PGADMIN_DEFAULT_EMAIL: () => 'admin@metiquo.fr',
    PGADMIN_DEFAULT_PASSWORD: () => randomBytes(32).toString('hex'),
    PGADMIN_PORT: () => '5050',
  };
  for (const [key, value] of Object.entries(defaults)) {
    if (!new RegExp(`^${key}=`, 'm').test(existing)) additions.push(`${key}=${value()}`);
  }
  if (additions.length) {
    await appendFile(path, `\n${additions.join('\n')}\n`);
    console.log('Existing settings preserved; missing auth/pgAdmin settings added.');
  } else console.log('.env.docker already exists; preserved.');
}
