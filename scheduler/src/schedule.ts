// GitHub's own cron is best-effort and was silent for hours on this new repo; a Worker Cron Trigger is not.
// The Worker fires every 5 minutes (UTC) and asks GitHub to run whichever workflows are due.

export interface Env {
  GITHUB_TOKEN: string;
  REPO: string;
}

export type Fetcher = (url: string, init: RequestInit) => Promise<Response>;

export function workflowsDue(at: Date): string[] {
  const minute = at.getUTCMinutes();
  const hour = at.getUTCHours();
  const due: string[] = [];
  if (minute % 15 === 5) due.push("archive.yml"); // :05 :20 :35 :50
  if (minute % 15 === 10) due.push("forecast.yml"); // :10 :25 :40 :55, five minutes after each archive
  if (hour === 18 && minute === 30) due.push("verify.yml"); // 02:30 Malaysia time
  if (at.getUTCDay() === 6 && hour === 19 && minute === 0) due.push("train.yml"); // Sunday 03:00 Malaysia time
  return due;
}

export async function dispatch(workflow: string, env: Env, fetcher: Fetcher): Promise<void> {
  const response = await fetcher(`https://api.github.com/repos/${env.REPO}/actions/workflows/${workflow}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "myhaze-scheduler",
    },
    body: JSON.stringify({ ref: "main" }),
  });
  if (!response.ok) throw new Error(`${workflow}: GitHub answered ${response.status}`);
}
