# Dev Notes

## Design

### Layout & Responsiveness
The application layout dynamically adapts to screen sizes to ensure full usability on both desktop and mobile devices.

- **Desktop Viewport (>= 768px)**:
  - Sidebar layout: Navbar on the left containing "Create Job", "Jobs", "Profiles", "Tools", and "Settings" anchored at the bottom.
  - Sidebar remains fixed while the main content area scrolls.
  - Current transcode status is displayed in a persistent footer at the bottom of the content area.
- **Mobile Viewport (< 768px)**:
  - Bottom navigation bar: Sidebar collapses to a bottom-docked navigation bar for ergonomic thumb reach, or a top header with hamburger menu.
  - Two-column layouts stack vertically to fit narrow viewports.
  - Interactive element touch targets are increased to a minimum of 48px.

### Individual Pages
- **Create Job**: 
  - *Desktop*: Two columns: file browser on the left (featuring an interactive delayed-search input bar and a library sync control button), profile selection and override on the right.
  - *Mobile*: Stacks vertically (file browser on top, profile selection below) or uses a tabbed interface.
- **Jobs**: 
  - *Desktop*: Full table showing all job metadata columns.
  - *Mobile*: Collapses to cards or displays only core columns (status, progress bar, file name) to avoid horizontal scrolling.
- **Profiles**: 
  - *Desktop*: Two columns: profile categories tree on the left, selected profile configuration form on the right.
  - *Mobile*: Stacks vertically (categories browser on top, configuration form below).
- **Tools**:
  - *Desktop*: Two columns: file browser on the left, dry-run tool configuration controls (FPS Deduplication or VMAF Scanner) and detailed result dashboard on the right.
  - *Mobile*: Stacks vertically (file browser on top, tool config and results below).
- **Settings**: 
  - Linear single-column layout containing all settings forms (including folders, system configurations, crash recovery behavior, and global Privacy Mode preferences), styled with responsive inputs.


### Logo

The logo should represent two gears churning through film spool.

## Features
Profiles:
- Codecs: libsvtav1, libx265, libx264
- Preset, CRF, visual tune, pixel format, FPS mode
- Selectable passthrough audio codecs, with fallback codec and bitrate
- Customizable output suffix incl. file collision
- Jobs queue
- **Host-Only Processing**: The application processes media files directly on the host filesystem (or mounts) ONLY. There is no web-based upload or download functionality; files are selected, transcoded, and stored locally within the configured media folders.
- **Default Privacy Mode**: Privacy Mode must be disabled by default. Users can explicitly enable it under application settings.
- **Search Feedback**: When a directory search yields no matches, the file browser must report context-specific feedback integrating the search term (e.g. `No file containing "BigBu" was found.`) to confirm search execution.
- **Active Navigation Highlighting**: The sidebar navigation links must dynamically highlight only the active page and adapt to client-side popstate changes.
- **UI Presentation**: The application logo remains static and does not animate. Preset overrides config forms are rendered directly below the profile preset selectors, with visual margins and paddings aligned.
- **Premium Dropdowns**: Dropdown select inputs (`select.form-control`) must use custom premium styling: a native arrow override (using `appearance: none`), a custom chevron SVG background indicator, matching focus transitions, and dark option background colors to align with the application's aesthetic.
- **Minimalist & Modern Design**: The visual styling must be clean, simple, and flat. It must avoid heavy visual noise, radial color gradients on the body, glows, shadows, and glassmorphic blur filters. Main backgrounds must use deep flat charcoal/black colors, components must use clean flat dark surfaces with thin borders, and primary interactive elements (like active tabs and buttons) must use clean flat solid highlights (such as crisp white or solid pastel violet accent details) to establish a premium and modern minimalist layout.

### Roadmap
- Hardware acceleration

## Implementation

### Profiles
There shall be profile categories, as well as the profiles themselves. The whole system shall be directory and file based. As this application will run dockerized, the user will mount an appdata directory. Inside this appdata directory shall be a "profiles" directory, where our profile categories are stored as directories, and the profiles are stored as TOML-based ".ebrake" files.  

Requirements:
- Profiles MUST be inside categories
- Categories CANNOT nest inside other categories
- The content of the profile files is TOML-based, sectioned into: video encoding, audio encoding, output formatting

Profile TOML content:
- Video encoding
  - Codec: libsvtav1, libx265, libx264
  - Preset: number or text, depending on codec
  - CRF: number (omitted if using VMAF auto-CRF selection)
  - Visual tune: number
  - FPS: "same as source" or number
  - FPS mode: constant or variable
  - Pixel format: "same as source" or yuv420p or yuv420p10le
- Optimization & Filters
  - Target VMAF: number (e.g. 93.0 or 95.0 to enable auto-CRF selection, or 0 / omitted to disable)
  - VMAF search range: min/max CRF limits (e.g. [18, 30])
  - Duplicate frame detection: boolean (true/false)
  - Duplicate threshold: float (e.g. 0.001 sensitivity)
- Audio encoding
  - Passthrough codecs: list of passthrough codecs
  - Fallback codec: name
  - Fallback bitrate: number
- Subtitles
  - Mode: "none", "passthrough", or "burn-in"
  - Languages: list of ISO-639-2 language codes to filter (e.g., ["eng", "ger"]), or ["all"]
  - Burn-in track select: "default" (first default track), "forced" (first forced track), or track index (integer)
- Output formatting
  - Output suffix: string
  - Container: name (e.g. mkv)

### Jobs SQL Schema
column | type | description
-------|------|------------
id | INTEGER | primary key
status | TEXT | `pending`, `running`, `completed`, `failed`, `cancelled`
created_at | DATETIME | when job was created
updated_at | DATETIME | when job was updated
started_at | DATETIME | when job was started
finished_at | DATETIME | when job was finished
failed_at | DATETIME | when job failed
cancelled_at | DATETIME | when job was cancelled
duration | INTEGER | time it took to complete in seconds
relative_size | INTEGER | output size as a percentage of input size
input_path | TEXT | input file path
output_path | TEXT | output file path
priority | INTEGER | job priority
transcode_next_position | INTEGER | custom position in the 'Transcode Next' queue (NULL if in normal queue)
category | TEXT | name of the preset category
preset | TEXT | name of the .ebrake preset used
is_customized | BOOLEAN | true if parameters were modified from the preset
preset_config | TEXT | full JSON representation of the final encoding parameters used
subtitle_mode | TEXT | subtitle handling mode: `none`, `passthrough`, `burn-in`
selected_subtitle_track | INTEGER | index of the subtitle track burned in or matched (NULL if none)
ffmpeg | TEXT | complete ffmpeg command
error | TEXT | error message
source_fps | REAL | detected original FPS of the source video
unduplicated_fps | REAL | effective FPS after removing duplicate frames
result_fps | REAL | final target FPS of the output video
target_vmaf | REAL | target VMAF score for automatic CRF selection (NULL if fixed CRF)
selected_crf | INTEGER | chosen CRF value (either fixed from profile, or determined via VMAF tests)
measured_vmaf | REAL | final measured average VMAF of the output file

### Media Files SQL Schema
column | type | description
-------|------|------------
path | TEXT | primary key (absolute path inside container)
name | TEXT | base filename or directory name
parent_path | TEXT | parent directory path
is_dir | BOOLEAN | true if directory, false if file
size | INTEGER | file size in bytes
mtime | DATETIME | modification timestamp

### File Browser Search & Indexing Design

To provide a robust, host-system-agnostic, and fast search feature in Docker that does not degrade disk I/O on slow network shares (SMB/NFS) during typing, a local SQLite-backed search architecture is used.

#### 1. Background File Scanner
- **Process**: A background scanner periodically walks the `/media` mount directory and stores the directory structure in the `media_files` table.
- **Triggering**:
  - Automatically runs every 30 minutes.
  - Can be manually triggered by a "Sync Library" button in the UI.
- **Scanning Algorithm**:
  - Uses Python's `os.scandir` for rapid directory traversal (retrieving file stats without additional system calls).
  - Operates inside a transaction:
    - **Identify**: Fetch all existing `path` values from `media_files` into memory (or compare in chunks).
    - **Upsert**: Insert or update discovered paths in bulk (using SQLite `INSERT OR REPLACE` in transactions of 1000 items).
    - **Prune**: Delete paths from the database that no longer exist on disk.
- **Index**: Create a B-tree index on the `name` column:
  ```sql
  CREATE INDEX idx_media_files_name ON media_files(name);
  ```

#### 2. Search API
- **Route**: `GET /api/media/search?q=query`
- **Logic**:
  - If the search query is empty, return the root/current directory listing from disk (fallback to real-time navigation).
  - If the query is present, query the database:
    ```sql
    SELECT * FROM media_files
    WHERE name LIKE :query
    ORDER BY is_dir DESC, name ASC
    LIMIT 100;
    ```
    *(where `:query` is padded with `%` wildcards, e.g., `%matrix%`)*.
  - Return the results rendered as a flat HTML list of file entries (folders and files) with icons representing their relative paths, allowing the user to select them directly.

#### 3. Frontend Integration (HTMX + Alpine.js)
- **Search Input**: Located in the file browser header.
  - Uses HTMX trigger delay to prevent overloading the backend:
    ```html
    <input type="text" name="q" placeholder="Search files..."
           hx-get="/api/media/search"
           hx-trigger="keyup changed delay:300ms"
           hx-target="#file-list"
           hx-indicator="#search-indicator" />
    ```
- **Sync Control**: A small "Sync" button next to the search input. Clicking it makes a `POST` request to `/api/media/sync`, triggering the scanner in the background and showing a progress spinner.

### Job Configuration Override & Serialization Design

To allow users to modify encoding settings for a specific job without creating clutter in their profile files, the application uses a DB-serialized override system.

#### 1. Serialization Flow
1. **Profile Load**: When the user selects a profile in the "Create Job" UI, the backend reads the corresponding `.ebrake` (TOML) file.
2. **Form Pre-fill**: The UI renders a configuration panel pre-filled with all parameters defined in the profile (CRF, preset, codecs, audio, etc.).
3. **UI Customization**: The user can alter any configuration inputs (e.g. override CRF from 22 to 25).
4. **Job Dispatch**: When the user clicks "Start Transcode" or "Add to Queue":
   - The frontend sends a `POST` request to `/api/jobs` containing:
     - `input_path`
     - `category` (selected profile category)
     - `preset` (selected profile name)
     - A payload of overridden values (or the entire compiled configuration set).
   - The backend validates the parameters and resolves the final configuration.
   - If any values differ from the original TOML profile, `is_customized` is set to `true`.
   - The resolved configuration is serialized as a JSON string and saved directly into the `preset_config` column of the `jobs` table.

#### 2. Robustness and Isolation Benefits
- **Deletion Resilience**: If the user later modifies or deletes the original `.ebrake` profile in the filesystem, all previously queued, running, or completed jobs remain executable and fully auditable because their execution parameters are frozen inside `preset_config`.
- **Easy Retry**: If a job fails or needs to be duplicated, the backend can reconstruct the exact same parameters by parsing `preset_config` rather than referencing external files.
- **Auditing UI**: The "Jobs" page details tab can display the exact configuration JSON used for that specific run, showing modified settings highlighted next to original profile defaults.

### Duplicate Frame Detection & VMAF Auto-CRF Design

This section details how the backend handles duplicate frame detection and automatic CRF selection using VMAF.

#### 1. Duplicate Frame Detection (Variable Frame Rate drop)
- **Methodology**: The engine uses the FFmpeg filter `mpdecimate` (or a custom threshold check) to detect and drop duplicate frames from the source during encoding.
- **Metrics Collected**:
  - **Source FPS**: Probed using `ffprobe` (e.g. `r_frame_rate` or `avg_frame_rate`).
  - **Unduplicated FPS**: Calculated as:
    $$\text{effective\_fps} = \frac{\text{total\_frames} - \text{dropped\_duplicate\_frames}}{\text{duration}}$$
    This indicates the actual unique content frame rate.
  - **Result FPS**: The frame rate of the output file. If output FPS mode is set to constant, it matches the configured FPS; if variable, it matches the unduplicated/source FPS.

#### 2. VMAF-based Automatic CRF Search
- **Problem**: Finding a CRF value that achieves a specific perceived quality (VMAF score) without encoding the entire file multiple times.
- **Search Process**:
  1. **Sampling**: Select 3 to 5 small segments from the input video (e.g., 10-second clips at 20%, 50%, and 80% of the video duration) to represent different levels of motion and detail.
  2. **Iteration**: Use an optimization algorithm (such as Binary Search or Secant Method) to run test transcodes of these sample segments.
     - *Start Bounds*: Typically `crf_min = 18` (high quality) and `crf_max = 32` (lower quality).
     - *Initial probe*: Run a test encode at the midpoint CRF (e.g., 25).
     - *Evaluation*: Calculate VMAF on the encoded samples against the original source samples using FFmpeg's `libvmaf` filter.
     - *Bisection*: Adjust CRF bounds based on the result:
       - If measured VMAF < Target VMAF: set `crf_max = current_crf` (we need higher quality / lower CRF).
       - If measured VMAF > Target VMAF: set `crf_min = current_crf` (we can accept lower quality / higher CRF).
     - *Termination*: Stop when $|VMAF_{measured} - VMAF_{target}| < 0.5$ or when the CRF bounds converge (max 3-4 iterations to conserve CPU/GPU time).
  3. **Execution**: Perform the full video transcode using the determined `selected_crf`.
  4. **Final Verification**: Run a final VMAF calculation over the completed file to record `measured_vmaf` in the database.

#### 3. Execution Pipeline & Alignment Gotchas
When combining duplicate frame detection (`mpdecimate`) and VMAF search, the execution sequence must be carefully controlled to prevent alignment issues. If one stream is decimated and the other is not, frame-by-frame VMAF comparison will mismatch and report incorrect (extremely low) quality scores.

**Pipeline Order**:
1. **Probe Source**: Retrieve source metadata (`duration`, `source_fps`).
2. **Execute VMAF Search** (if Target VMAF > 0):
   - For each search iteration:
     - Extract sample clips from the source.
     - Transcode the sample clips using the candidate CRF. If duplicate detection is enabled, apply `mpdecimate` in this test transcode filter chain.
     - **Frame Alignment**: Compare the test transcode against the original source clips. To ensure `libvmaf` compares the correct frames:
       - Both the reference stream and the transcoded stream must pass through the identical `mpdecimate` filters in the filtergraph, or
       - The streams must be explicitly synchronized using PTS/FR (e.g. via `setpts` or matching filter paths) so that dropped frames in the transcode are matched against the same frames dropped in the reference.
3. **Execute Full Transcode**:
   - Run the full transcode with the chosen `selected_crf`. Apply `mpdecimate` if duplicate detection is enabled.
4. **Post-Transcode Metrics & Verification**:
   - Probe the output to get `result_fps` and calculate the actual `unduplicated_fps`.
   - Run a final VMAF pass on the completed video to save `measured_vmaf` to the database (applying matching decimation to reference and output to keep them aligned).

### Subtitle Handling Design

This section details how the application handles subtitle passthrough, mapping, container-specific constraints, and video burn-in.

#### 1. Metadata Probing
Before launching a transcode, the backend probes the input file using `ffprobe` to build a list of available subtitle tracks:
- **Metrics Collected per Track**:
  - `index`: Stream index in the file (e.g. `0:3` or just index `3`).
  - `codec`: e.g., `subrip` (SRT), `ass`, `hdmv_pgs_subtitle` (PGS), `dvd_subtitle` (VOBSUB).
  - `language`: ISO-639-2 language tag (e.g., `eng`, `fre`, `ger`).
  - `flags`: Boolean checks for `default` and `forced` streams.

#### 2. Subtitle Processing Modes

##### Mode A: `none`
No subtitles are mapped or burned. The output will contain only video and audio streams.
- **FFmpeg Flag**: Omit subtitle mapping flags entirely.

##### Mode B: `passthrough` (Soft Subtitles)
Subtitles are copied as metadata streams into the output container.
- **MKV (Matroska) Output**:
  - MKV supports almost all subtitle formats natively.
  - **FFmpeg Flags**: Map all subtitles optionally and copy the codecs:
    ```bash
    -map 0:s? -c:s copy
    ```
- **MP4 Output**:
  - MP4 does not support PGS or SRT streams natively. All text-based subtitles must be converted to `mov_text`. Image-based subtitles (PGS, VOBSUB) must be dropped or burned in.
  - **FFmpeg Flags**: Convert text subtitles to `mov_text` and drop image subtitles:
    ```bash
    -map 0:s? -c:s mov_text
    ```

##### Mode C: `burn-in` (Hard Subtitles)
The selected subtitle track is overlaid directly on the video frames. This requires re-encoding the video.
- **Text-Based Subtitles (SRT, ASS)**:
  - To avoid Windows path escaping bugs (with colons and backslashes in `-vf subtitles`), use FFmpeg's stream index reference syntax:
    ```bash
    -vf "subtitles=input_file.mkv:si=track_index"
    ```
- **Image-Based Subtitles (PGS, VOBSUB)**:
  - These cannot be parsed by the `subtitles` filter. Instead, use a dual-input `-filter_complex` overlay graph:
    ```bash
    ffmpeg -i input.mkv -filter_complex "[0:v][0:s:track_index]overlay[v]" -map "[v]" ...
    ```

### Standalone Tools (Dry-Runs)

The "Tools" tab provides standalone utility calculators. These do not create database jobs or write permanent output video files. They run as background task processes in FastAPI, returning status updates and results interactively via the UI.

#### 1. FPS Deduplication Dry-Run
- **Objective**: Determine the number of duplicate frames and the resulting unduplicated frame rate without running a transcode.
- **Backend Operation**:
  - To optimize execution times on full-length movies while avoiding false positive detections, a duration threshold of **180 seconds (3 minutes)** is used:
    - **Short Videos (<= 180s)**: A full scan is executed using strict, conservative `mpdecimate` settings to guarantee 100% precision.
    - **Long Videos (> 180s)**: High-speed robust temporal sampling is performed. The video is split into **15 evenly spaced 15-second segments** inside the middle 70% of the video (from 15% to 85% of total duration to avoid intro/outro credits).
  - High-speed seeks (using input seek `-ss` before `-i`) are executed for each sample segment:
    ```bash
    ffmpeg -y -ss [start_time] -t 15.0 -i [input_path] -vf mpdecimate=max=0:hi=64:lo=64:frac=0.001 -f null -
    ```
    - **Strict Filtering**: By passing `max=0:hi=64:lo=64:frac=0.001`, we restrict frame drops to almost completely identical frames (less than `0.1%` block changes). This avoids dropping low-motion content (talking heads, slow pans) which defaults (`frac=0.33`) would aggressively drop.
  - **Outlier Rejection (Trimmed Mean)**: The duplicate ratios for all 15 segments are collected, sorted, and the top **3** (e.g. black transition frames, static scenes) and bottom **3** (e.g. action scenes) segments are discarded. The remaining 9 segments are averaged to calculate the final duplicate ratio.
  - The duplicate ratio is mathematically extrapolated to the total frame count, completely eliding slow full-file packet copy counting passes.
  - Return:
    - Total Source Frames
    - Total Unique Frames
    - Dropped Duplicate Frames
    - Source FPS vs. Calculated Unduplicated FPS
    - Saved Space Estimation (based on percentage of frames dropped)

#### 2. Standalone VMAF Scanner
- **Objective**: Measure the VMAF score for a specific encoding configuration (codec, preset, CRF, pixel format) without performing a full transcode.
- **Backend Operation**:
  - The user enters parameters: `CRF`, `Codec`, `Preset`, `Pixel Format`.
  - The system performs a test transcode *only* on sample segments of the video (e.g., three 10-second clips) to a temporary location using those parameters.
  - VMAF comparison is computed on the test samples against the original source samples (applying matching filters like `mpdecimate` if duplicate detection is enabled to ensure correct frame alignment).
  - Return:
    - Measured VMAF Score
    - Bitrate estimate of the samples
    - File size scaling estimate (output size % of input size)

### Queue and 'Transcode Next' Ordering Design

The application maintains a dual-queue system using a single SQLite table (`jobs`). 

1. **Normal Queue**: All pending jobs (`status = 'pending'`) where `transcode_next_position IS NULL`.
   - **Ordering Rule**: Ordered by `priority DESC` primarily, and `created_at ASC` secondarily.
2. **"Transcode Next" Queue**: All pending jobs (`status = 'pending'`) where `transcode_next_position IS NOT NULL`.
   - **Ordering Rule**: Ordered by `transcode_next_position ASC`.
   - Items in this queue always take precedence over normal queue items, acting like "Play Next" in media players.

---

#### 1. Fetching the Queue (Unified)

To fetch all pending jobs in their correct execution order:

```sql
SELECT *
FROM jobs
WHERE status = 'pending'
ORDER BY
  -- Transcode Next jobs always come first
  CASE WHEN transcode_next_position IS NOT NULL THEN 0 ELSE 1 END ASC,
  -- Order Transcode Next jobs by their custom position
  transcode_next_position ASC,
  -- Order normal queue jobs by priority (highest first) and created_at (oldest first)
  priority DESC,
  created_at ASC;
```

---

#### 2. Queue Operations & SQLite Queries

All list modification queries should be executed within a database transaction to maintain sequence integrity.

##### A. Move to "Transcode Next" (Append to bottom)
To move a job (`:job_id`) from the normal queue to the end of the "Transcode Next" queue:

```sql
-- 1. Determine the next available position index (default to 0 if queue is empty)
SELECT COALESCE(MAX(transcode_next_position) + 1, 0) AS next_pos
FROM jobs
WHERE status = 'pending' AND transcode_next_position IS NOT NULL;

-- 2. Update the target job's position with next_pos
UPDATE jobs
SET transcode_next_position = :next_pos
WHERE id = :job_id AND status = 'pending';
```

##### B. Move/Insert to "Transcode Next" at a Specific Position
To insert a job `:job_id` into "Transcode Next" at a specific index `:target_pos` (e.g., when dragging from normal queue to a specific slot):

```sql
-- 1. Shift existing items at or below the target position down (increment position)
UPDATE jobs
SET transcode_next_position = transcode_next_position + 1
WHERE status = 'pending' 
  AND transcode_next_position >= :target_pos;

-- 2. Assign the target position to the job
UPDATE jobs
SET transcode_next_position = :target_pos
WHERE id = :job_id AND status = 'pending';
```

##### C. Drag'n'Drop Reordering within "Transcode Next"
When dragging an item with `:job_id` from `:from_pos` to `:to_pos` inside the "Transcode Next" queue:

- **Case 1: Dragging upwards (`:from_pos > :to_pos`)** (e.g., moving item 3 to position 1):
  ```sql
  -- Shift elements in between down to make space
  UPDATE jobs
  SET transcode_next_position = transcode_next_position + 1
  WHERE status = 'pending'
    AND transcode_next_position >= :to_pos
    AND transcode_next_position < :from_pos;

  -- Set new position for dragged job
  UPDATE jobs
  SET transcode_next_position = :to_pos
  WHERE id = :job_id;
  ```

- **Case 2: Dragging downwards (`:from_pos < :to_pos`)** (e.g., moving item 1 to position 3):
  ```sql
  -- Shift elements in between up to close the gap
  UPDATE jobs
  SET transcode_next_position = transcode_next_position - 1
  WHERE status = 'pending'
    AND transcode_next_position > :from_pos
    AND transcode_next_position <= :to_pos;

  -- Set new position for dragged job
  UPDATE jobs
  SET transcode_next_position = :to_pos
  WHERE id = :job_id;
  ```

##### D. Remove from "Transcode Next" (Move back to normal queue)
When removing a job `:job_id` with position `:current_pos` from the "Transcode Next" queue (setting it back to normal priority-based ordering):

```sql
-- 1. Clear the custom position
UPDATE jobs
SET transcode_next_position = NULL
WHERE id = :job_id;

-- 2. Close the gap for subsequent items
UPDATE jobs
SET transcode_next_position = transcode_next_position - 1
WHERE status = 'pending'
  AND transcode_next_position > :current_pos;
```

---

#### 3. Automatic Lifecycle Maintenance

To keep the indices compact and sequential, when a job in "Transcode Next" begins running or is cancelled/failed/deleted, we must clean up the list indices.

##### When a job starts transcoding:
```sql
-- 1. Fetch the next pending job ID and its transcode_next_position
SELECT id, transcode_next_position
FROM jobs
WHERE status = 'pending'
ORDER BY
  CASE WHEN transcode_next_position IS NOT NULL THEN 0 ELSE 1 END ASC,
  transcode_next_position ASC,
  priority DESC,
  created_at ASC
LIMIT 1;

-- 2. If the selected job had a non-NULL :started_pos:
-- Update status
UPDATE jobs
SET status = 'running',
    started_at = CURRENT_TIMESTAMP,
    transcode_next_position = NULL
WHERE id = :job_id;

-- Shift down the remaining items to close the gap
UPDATE jobs
SET transcode_next_position = transcode_next_position - 1
WHERE status = 'pending'
  AND transcode_next_position > :started_pos;
```

##### When a pending job in "Transcode Next" is cancelled, failed, or deleted:
Use the same logic as "Remove from Transcode Next" to set `transcode_next_position = NULL` (or delete the job record) and decrement the position of all items with `transcode_next_position > :removed_pos`.

---

#### 4. Frontend Integration (HTMX + Alpine.js + Sortable.js)

- **Sortable.js Integration**: Use `Sortable.js` (or Alpine's drag'n'drop wrapper) to enable dragging list items.
- **Drag & Drop Events**:
  - When sorting within "Transcode Next", the frontend fires a `POST` request to `/api/jobs/reorder` with the body `{ job_id, from_pos, to_pos }`.
  - When dragging from the Normal Queue into "Transcode Next", it fires a `POST` request to `/api/jobs/transcode-next` with `{ job_id, target_pos }`.
  - When dragging out of "Transcode Next" (or clicking a "Remove" button), it fires a `DELETE` or `POST` request to `/api/jobs/transcode-next/{job_id}`.
- **HTMX UI Updates**: 
  - After a successful reordering or insertion operation, the backend returns the updated HTML structure for the active queues using HTMX out-of-band swaps or simple template refreshes.

---

### Startup Recovery & Crash Handling Design

Since this app executes long-running FFmpeg processes dockerized, it must handle unexpected interruptions gracefully (e.g. Docker host reboot, container crash, backend crash, or user-initiated force-stop).

#### 1. Configuration Setting
Add a global setting `on_startup_orphaned_job_action` in the settings configuration:
- **Options**:
  - `mark_failed_pause` (Default): Mark the interrupted job as `failed` and do not process the next jobs in the queue automatically.
  - `mark_failed_resume`: Mark the interrupted job as `failed` and automatically trigger the queue worker to process the next `pending` job.
  - `auto_restart`: Remove the incomplete output file, set the job's status back to `pending`, and immediately re-run it.

---

#### 2. Startup Boot Sequence
During application startup (e.g., FastAPI `@app.on_event("startup")` handler), the backend runs the following initialization checks:

```sql
-- 1. Identify any jobs left in the 'running' state on boot
SELECT id, output_path FROM jobs WHERE status = 'running';
```

For each orphaned job found, execute the recovery logic based on the user setting:

##### Action: `mark_failed_pause` or `mark_failed_resume`
```sql
-- Mark the job as failed with a diagnostic error message
UPDATE jobs
SET status = 'failed',
    failed_at = CURRENT_TIMESTAMP,
    error = 'Job interrupted due to unexpected application shutdown or container restart'
WHERE id = :job_id;
```
- If set to `mark_failed_resume`, trigger the queue worker:
  `POST /api/queue/start` (internal endpoint).

##### Action: `auto_restart`
1. **Clean up partial files**: The backend checks if a file exists at `output_path`. If it does, the backend deletes it to prevent output corruption.
2. **Re-queue the job**:
   ```sql
   UPDATE jobs
   SET status = 'pending',
       started_at = NULL,
       error = NULL
   WHERE id = :job_id;
   ```
3. **Trigger Queue**: Invoke the queue worker to begin transcoding.

---

### Privacy Mode & Obfuscation Design

To support running the application in public settings (e.g., transit, cafes, offices) without disclosing the titles of active transcoding jobs, the app implements a toggleable **Privacy Mode**.

#### 1. Configuration Settings & State
- **Global Setting**: A persistent setting `privacy_mode_enabled` (boolean) inside the Settings tab.
- **Transient Session State**: An in-memory, tab-local toggle called `privacy_snoozed` (boolean).
  - Managed fully client-side via Alpine.js global store (`Alpine.store('privacy')`) or sessionStorage.
  - Reset to `false` (meaning privacy remains active if globally enabled) on page reload, tab closure, or opening the app in a new window/browser.

---

#### 2. Visual Layout & HTML CSS Classes
The UI implements styling-based obfuscation to keep the interface fast and interactive:
- **Global CSS Class**: If the global setting is `true`, the main page layout `<body>` is rendered with the class `privacy-enabled`.
- **Alpine Store Integration**:
  - The navbar contains a toggle button (e.g. eye icon `eye-slash`/`eye`) that reads and writes `sessionStorage.getItem('privacy_snoozed')`.
  - On page load, Alpine.js initializes a body attribute `:class="{'privacy-active': $store.privacy.active && !$store.privacy.snoozed}"`.
- **Sensitive Fields**: Any HTML elements containing paths, file names, ffmpeg arguments, category names, or error logs are tagged with the CSS utility class `.privacy-sensitive`.
- **CSS Obfuscation Styling**:
  ```css
  /* When privacy mode is active and NOT snoozed, obfuscate sensitive text */
  .privacy-active .privacy-sensitive {
      filter: blur(6px);
      user-select: none;
      transition: filter 0.2s ease;
  }
  
  /* Prevent copy-pasting blurred content while active */
  .privacy-active .privacy-sensitive * {
      pointer-events: none;
  }
  ```

---

#### 3. Quick-Snooze Action Control
- **Navbar Button**: Located in a visible area of the sidebar/header (next to layout links).
- **Behavior**:
  - Clicking the toggle button calls a JS method: `Alpine.store('privacy').toggleSnooze()`.
  - This toggles the `privacy_snoozed` state. When snoozed, the `.privacy-active` class is removed from the layout, instantly de-blurring all text fields.
  - The snooze button changes visually (e.g., eye icon turns green or open-eye symbol).
- **Security Check**: The snooze state is stored strictly in `sessionStorage` (which persists across soft navigations but clears on tab reload or exit), ensuring that opening the app in a new tab or reloading the page automatically locks/reenables the privacy blur immediately.

---

## API Reference & Implementation Blueprint (AI Agent Optimized)

This section provides strict specifications for database initialization and REST/HTMX routes. Implementation agents must follow these exact schemas and routes.

### 1. Database Initialization Schema
```sql
-- Jobs Table
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME,
    finished_at DATETIME,
    failed_at DATETIME,
    cancelled_at DATETIME,
    duration INTEGER,
    relative_size INTEGER,
    input_path TEXT NOT NULL,
    output_path TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    transcode_next_position INTEGER UNIQUE, -- NULL allowed, values are 0-indexed sequence numbers
    category TEXT,
    preset TEXT,
    is_customized BOOLEAN NOT NULL DEFAULT 0 CHECK(is_customized IN (0, 1)),
    preset_config TEXT, -- JSON string containing final resolved profile params
    subtitle_mode TEXT NOT NULL CHECK(subtitle_mode IN ('none', 'passthrough', 'burn-in')),
    selected_subtitle_track INTEGER,
    ffmpeg TEXT,
    error TEXT,
    source_fps REAL,
    unduplicated_fps REAL,
    result_fps REAL,
    target_vmaf REAL,
    selected_crf INTEGER,
    measured_vmaf REAL
);

-- Media Files Table (Search Cache)
CREATE TABLE IF NOT EXISTS media_files (
    path TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    parent_path TEXT NOT NULL,
    is_dir BOOLEAN NOT NULL CHECK(is_dir IN (0, 1)),
    size INTEGER NOT NULL DEFAULT 0,
    mtime REAL NOT NULL -- modification timestamp as float
);
CREATE INDEX IF NOT EXISTS idx_media_files_name ON media_files(name);

-- Settings Table (Persistent Key-Value Store)
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL -- Serialized value (e.g. JSON string or plain text)
);

-- Insert Default System Settings
INSERT OR IGNORE INTO settings (key, value) VALUES 
('on_startup_orphaned_job_action', '"mark_failed_pause"'),
('privacy_mode_enabled', 'false');
```

---

### 2. FastAPI API Router Reference

| Method | Endpoint | Request Payload | Return Type | Description |
|--------|----------|-----------------|-------------|-------------|
| **GET** | `/api/media/search` | Query params: `q: str` | HTML Snippet | Runs SQLite search on cached filenames. Returns filtered file browser rows. |
| **POST** | `/api/media/sync` | None | HTML (toast/spinner) | Triggers the background directory walker (`os.scandir`) to refresh `media_files`. |
| **POST** | `/api/jobs` | JSON (Paths, presets, overrides) | HTML (queue row) | Validates preset parameters, generates ffmpeg template, writes to database. |
| **POST** | `/api/jobs/reorder` | JSON: `{job_id, from_pos, to_pos}` | HTML (updated queue) | Reorders queue items within the "Transcode Next" list. |
| **POST** | `/api/jobs/transcode-next` | JSON: `{job_id, target_pos}` | HTML (updated queue) | Inserts a job into "Transcode Next" at a specific index. |
| **DELETE** | `/api/jobs/transcode-next/{id}` | None | HTML (updated queue) | Removes a job from "Transcode Next" back to priority ordering. |
| **POST** | `/api/queue/start` | None | HTML (queue status) | Triggers the next pending transcode worker job loop. |
| **GET** | `/api/settings` | None | HTML Form | Returns settings configuration input layout. |
| **POST** | `/api/settings` | Form fields | HTML Form | Updates global settings (e.g., Privacy Mode, Crash Recovery) in the database. |

---

### 3. Frontend Store Blueprint (Alpine.js)

Provide a global store for state persistence across the page lifecycle:
```javascript
document.addEventListener('alpine:init', () => {
    Alpine.store('privacy', {
        active: false, // Populated on boot from server-rendered body attribute
        snoozed: sessionStorage.getItem('privacy_snoozed') === 'true',
        
        init() {
            this.active = document.body.classList.contains('privacy-enabled');
        },
        
        toggleSnooze() {
            this.snoozed = !this.snoozed;
            sessionStorage.setItem('privacy_snoozed', this.snoozed ? 'true' : 'false');
        }
    });
});
```

---

## Verification & Testing

To ensure the application operates correctly, two automated verification suites are available:

1. **Lightweight Sanity Check (`verify.py`)**: A fast, dependency-free backend sanity check to test database storage, directory creation, default profile parser parsing, and basic queue sequencing without spawning any subprocesses or transcoding videos.
2. **Robust Integration Suite (`verify_integration.py`)**: A full end-to-end integration suite that programmatically generates synthetic media files with repeated frames and subtitle tracks, runs actual `ffmpeg` and `ffprobe` processes in a sandboxed environment, tests transcoding pipelines, and simulates web API requests.

### verify.py Capabilities

Currently, `verify.py` validates the following functionalities:

- **Setup & Initialization (`test_setup`)**:
  - **Directory Creation**: Verifies that `init_directories()` successfully creates required app folders.
  - **Database Setup**: Verifies that `init_db()` creates the SQLite database at `DB_PATH`.
  - **Settings CRUD**: Validates that system configuration read/write operations work by setting and getting a test key.
  - **Profile Configuration**: Loads the profile manager via `init_profiles()` and ensures that the categories list includes the `"Default"` category, and that the `"AV1 VMAF Auto-CRF"` profile correctly parses the SVT-AV1 codec settings.
- **Queue and 'Transcode Next' Scheduling (`test_queues`)**:
  - **Priority Ordering**: Creates two pending jobs and verifies they are sorted in descending order of priority.
  - **Transcode Next Insertion**: Promotes a lower-priority job to "Transcode Next" and asserts that it takes precedence at the front of the queue.
  - **Atomic Worker Processing**: Tests `start_next_job()` to confirm that it updates the job status to `running` atomically, returns the correct job, and correctly handles queue gap-compaction.
  - **Cleanup**: Verifies job deletion works as expected.
- **Library Scanner (`test_scanner`)**:
  - **Sync Run**: Runs `run_library_sync()` to ensure it successfully scans media folders without raising unexpected exceptions.

### verify_integration.py Capabilities

This script creates a sandboxed DB and app data space to execute complete integration tests:

- **Asset Generation**: Automatically constructs a 5-second 25fps Matroska container (`temp_input.mkv`) with repeated video frames (duplicates) and soft subtitle tracks using local `ffmpeg`.
- **E2E Transcoding Checks**:
  - **H.264 Transcoding**: Converts MKV input to MP4 using H.264 video codec and asserts output existence.
  - **Duplicate Frame Detection**: Runs SVT-AV1 transcode with `mpdecimate` filter active, and asserts that the measured `unduplicated_fps` is appropriately reduced compared to the source.
  - **VMAF Auto-CRF Optimization**: Performs multi-pass binary search CRF optimization against target VMAF scores using `libvmaf` filter (automatically skipped if `libvmaf` is missing from the container's FFmpeg build).
  - **Subtitle Burn-in**: Runs video burn-in transcode and verifies correct subtitle track matching and mapping using subtitle-specific track index offsets.
- **Standalone Tools Dry-Runs**:
  - Validates direct function calls to `run_dedup_dryrun()` and `run_vmaf_search()`.
- **FastAPI Web API Route Simulation**:
  - Mocks FastAPI Request objects to test `/api/settings` and `/api/media/search` endpoints and their HTMX templates rendering.
- **Environment Cleanups**: Purges all intermediate assets and databases upon completion.