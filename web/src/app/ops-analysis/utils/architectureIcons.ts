export const CMDB_ISOMETRIC_ICON_SOURCE = 'icons-realistic';

export interface CmdbIconCandidate {
  key: string;
  describe?: string;
  source: string;
  src: string;
}

export interface IsopackIconCandidate {
  id: string;
  name: string;
  url: string;
  isIsometric?: boolean;
}

export interface CmdbIsometricIcon {
  id: string;
  name: string;
  src: string;
  isIsometric: true;
}

export interface ArchitecturePaletteIcon {
  id: string;
  name: string;
  url: string;
  isIsometric: true;
}

const uniqueById = <T extends { id: string }>(icons: T[]): T[] =>
  icons.filter(
    (icon, index, self) => index === self.findIndex((item) => item.id === icon.id)
  );

export const selectCmdbIsometricIcons = (
  icons: CmdbIconCandidate[]
): CmdbIsometricIcon[] =>
  uniqueById(
    icons
      .filter((icon) => icon.source === CMDB_ISOMETRIC_ICON_SOURCE)
      .map((icon) => ({
        id: `cmdb-${icon.key}`,
        name: icon.describe || icon.key,
        src: icon.src,
        isIsometric: true as const,
      }))
  );

export const selectIsometricIsopackIcons = (
  icons: IsopackIconCandidate[]
): ArchitecturePaletteIcon[] =>
  uniqueById(
    icons
      .filter((icon) => icon.isIsometric === true)
      .map((icon) => ({
        id: icon.id,
        name: icon.name,
        url: icon.url,
        isIsometric: true as const,
      }))
  );
