# #0015 Alarm family lint failed after the assign-modal merge because the new modal demo uses Button without importing it from antd.

- 2026-07-09T07:31:43Z `issue`: Alarm family lint failed after the assign-modal merge because the new modal demo uses Button without importing it from antd. [web/src/stories/alarm-family.stories.tsx]
- 2026-07-09T07:32:02Z `attempt`: Fixed the assign-modal family lint error by importing Button from antd for the new AlarmAssignModalDemo controls. [web/src/stories/alarm-family.stories.tsx] (worked)
- 2026-07-09T07:32:30Z `fix`: Alarm family now owns AlarmAssignModal workflow states; alarm-family lint passes after importing Button, diff check is clean, and the standalone alarm-assign-modal story file is gone. [web/src/stories/alarm-family.stories.tsx]
