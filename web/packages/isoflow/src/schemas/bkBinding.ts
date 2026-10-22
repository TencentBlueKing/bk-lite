import { z } from 'zod';

export const bkBindingSchema = z.object({
  inst_uuid: z.string(),
  model_id: z.string()
});
