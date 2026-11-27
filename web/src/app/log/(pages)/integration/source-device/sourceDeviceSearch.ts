import { buildSearchJumpUrl } from '@/app/log/(pages)/event/alert/buildSearchJumpUrl';
import { SyslogSourceDeviceRow } from '@/app/log/types/syslogSourceDevice';

export function buildSourceDeviceSearchUrl(
  row: Pick<
    SyslogSourceDeviceRow,
    'search_query' | 'search_start' | 'search_end'
  >
): string {
  return buildSearchJumpUrl({
    fallbackQuery: row.search_query,
    fallbackStart: row.search_start,
    fallbackEnd: row.search_end
  });
}
