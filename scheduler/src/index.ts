import { dispatch, type Env, workflowsDue } from "./schedule";

interface ScheduledController {
  scheduledTime: number;
}

export default {
  async scheduled(controller: ScheduledController, env: Env): Promise<void> {
    // Awaited, so a failed dispatch marks this cron run as failed in Cloudflare's logs.
    await Promise.all(workflowsDue(new Date(controller.scheduledTime)).map((w) => dispatch(w, env, fetch)));
  },
};
