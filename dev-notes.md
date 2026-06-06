# Dev Notes

## Design
- Navbar on the left: "Create Job", "Jobs", "Profiles", and "Settings" at the bottom
- Current transcode status as footer

Individual pages:
- Create Job: 
  - Left side: file browser
  - Right side: profile selection and override
- Jobs: Table of jobs
- Profiles: 
  - Left side: Small profile categories browser - categories as folders with profiles inside
  - Right side: the actual currently selected profile configuration
- Settings: simply all settings one after the other

### Logo

The logo should represent two gears churning through film spool.

## Features
Profiles:
- Codecs: libsvtav1, libx265, libx264
- Preset, CRF, visual tune, pixel format, FPS mode
- Selectable passthrough audio codecs, with fallback codec and bitrate
- Customizable output suffix incl. file collision
- Jobs queue

### Roadmap
- Search in the file browser
- Responsive design
- Duplicate frames detection
- VMAF
- Privacy setting / Obfuscation
- Subtitle handling
- Hardware acceleration

## Implementation

### Profiles
There shall be profile categories, as well as the profiles themselves. The whole system shall be directory and file based. As this application will run dockerized, the user will mount an appdata directory. Inside this appdata directory shall be a "profiles" directory, where our profile categories are stored as directories and the profiles are stored as TOML-based ".ebrake" files.  

Requirements:
- Profiles MUST be inside categories
- Categories CANNOT nest inside other categories
- The content of the profile files is TOML-based sectioned into: video encoding, audio encoding, output formatting

Profile TOML content:
- Video encoding
  - Codec: libsvtav1, libx265, libx264
  - Preset: number or text, depending on codec
  - CRF: number
  - Visual tune: number
  - FPS: "same as source" or number
  - FPS mode: constant or variable
  - Pixel format: "same as source" or yuv420p or yuv420p10le
- Audio encoding
  - Passthrough codecs: list of passthrough codecs
  - Fallback codec: name
  - Fallback bitrate: number
- Output formatting
  - Output suffix: string
  - Container: name (e.g. mkv)