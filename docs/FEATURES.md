# Feature coverage and external prerequisites

This is the complete original 129-feature product scope. A roadmap entry is **not** an implemented control. The registry distinguishes verified core capabilities from unfinished work. Entries marked `implemented` include evidence and describe their actual limits; partial foundations remain `pending`. No model-backed speech, semantic highlights, generative video or private YouTube workflow is claimed complete.

## Current decisions

- One private owner using multiple devices, not twenty separate users.
- A calm, editable theme and responsive, accessible controls.
- URL-first YouTube workflow; output downloads contain generated clips only.
- 720p–1080p H.264 MP4 is sufficient initially. 4K remains a later roadmap item.
- All available languages of the installed/selected speech provider, standard voices plus consented voice cloning, stock and generated B-roll are requested.
- AI proposes important edits for owner approval.
- Open-source first; no Google Cloud Console, Google Drive setup, or initial paid API budget.
- Keep only previous input URLs persistently. Source media, clips, timeline state and processing files are temporary and expire. A live process needs temporary video bytes to decode and render; this is not a permanent media library.
- Deliver in verified phases. Public deployment and permanent GPU/CPU hosting are separate requirements; open-source code does not guarantee free hosting.

## Status definitions

| Status | Meaning |
| --- | --- |
| implemented | Production behavior and relevant verification exist; evidence must be recorded. |
| pending | Required and not yet implemented/verified. |
| blocked | A specific missing model, provider, permission, network destination or credential prevents verification. |
| scope-conflict | A later instruction conflicts with the original list; preserve the item and explain the conflict. |

## Prerequisite decisions already made

No plugin installation is needed for FFmpeg, yt-dlp, ordinary editor UI or a self-hosted API. A chat plugin is not automatically a backend service usable by a deployed website. Inspect a plugin's actual capabilities before claiming it supplies a feature.

Missing provider access must not be worked around with invented results. Do not collect account passwords or export personal browser cookies. Use provider-supported authorization. Private YouTube account metadata does not establish permission or a method to fetch private video bytes.

Models for transcription, multimodal understanding, tracking, voice cloning, generation and upscaling need weights, licensing checks, RAM/VRAM, time and empirical output tests. Some open-source models can be run without an API bill, but compute and hosting still have costs.

Official social publishing and analytics require platform application registration and scopes. Voice cloning needs the owner's explicit consent to the specific voice workflow. Stock assets require usable licences. Never call a post, schedule, analytics result, clip score or generation successful without an actual result.

## Verified core and remaining work

Current coverage: **30 implemented, 62 pending, 25 blocked, 12 scope conflicts**. These statuses cover the original numbered requirements; additional reliability and security work is not inflated into extra feature counts.

The verified core includes manual segment editing/reordering, real text/caption rendering, aspect-ratio conversion, deterministic audio filtering, silence proposals with owner approval, 720p/1080p output, temporary renaming, upload, clip/ZIP downloads, and private editing/metadata/export APIs. The next verified stage adds short segment fades, temporary logo/music/font uploads, looped/mixed background music, caption font/colors and corner logos. Actual rendered pixels, decoded audio and browser workflows verify the output. Scene-cut detection, preview normalization, cancellation, resource limits and temporary cleanup support that workflow. They do not establish that semantic AI, generative media, all imports or social integrations work.

Tests and source-level evidence are recorded in each implemented entry of `features.json`. The application exposes this same registry so unfinished work stays visible.

## All original requirements

Machine-readable detail, including dependencies and conflict notes, is in [features.json](features.json).

| ID | Original feature | Group | Current status |
| --- | --- | --- | --- |
| 1 | ClipAnything AI | AI VIDEO UNDERSTANDING & HIGHLIGHT DETECTION | pending |
| 2 | Multimodal Video Analysis | AI VIDEO UNDERSTANDING & HIGHLIGHT DETECTION | pending |
| 3 | Visual Scene Recognition | AI VIDEO UNDERSTANDING & HIGHLIGHT DETECTION | pending |
| 4 | Speech Recognition | AI VIDEO UNDERSTANDING & HIGHLIGHT DETECTION | blocked |
| 5 | Emotion Detection | AI VIDEO UNDERSTANDING & HIGHLIGHT DETECTION | pending |
| 6 | Audio Event Recognition | AI VIDEO UNDERSTANDING & HIGHLIGHT DETECTION | pending |
| 7 | Contextual Video Understanding | AI VIDEO UNDERSTANDING & HIGHLIGHT DETECTION | pending |
| 8 | AI Virality Scoring | AI VIDEO UNDERSTANDING & HIGHLIGHT DETECTION | pending |
| 9 | Automatic Highlight Extraction | AI VIDEO UNDERSTANDING & HIGHLIGHT DETECTION | pending |
| 10 | AI Copilot | AI VIDEO UNDERSTANDING & HIGHLIGHT DETECTION | pending |
| 11 | Topic-Based Clipping | AI VIDEO UNDERSTANDING & HIGHLIGHT DETECTION | pending |
| 12 | Keyword-Based Clipping | AI VIDEO UNDERSTANDING & HIGHLIGHT DETECTION | pending |
| 13 | Action-Based Clipping | AI VIDEO UNDERSTANDING & HIGHLIGHT DETECTION | pending |
| 14 | Cross-Scene Highlight Compilation | AI VIDEO UNDERSTANDING & HIGHLIGHT DETECTION | pending |
| 15 | AI Narrative Structuring | AI VIDEO UNDERSTANDING & HIGHLIGHT DETECTION | pending |
| 16 | Automatic Teaser Generation | AI VIDEO UNDERSTANDING & HIGHLIGHT DETECTION | pending |
| 17 | Prompt-Based Clip Refinement | AI VIDEO UNDERSTANDING & HIGHLIGHT DETECTION | pending |
| 18 | Custom Clip Duration | AI VIDEO UNDERSTANDING & HIGHLIGHT DETECTION | implemented |
| 19 | Long-to-Short Video Conversion | AI VIDEO CLIPPING & EDITING | pending |
| 20 | Automatic Video Segmentation | AI VIDEO CLIPPING & EDITING | pending |
| 21 | Text-Based Video Editing | AI VIDEO CLIPPING & EDITING | blocked |
| 22 | Timeline-Based Editing | AI VIDEO CLIPPING & EDITING | implemented |
| 23 | Scene Reordering | AI VIDEO CLIPPING & EDITING | implemented |
| 24 | Scene Extension | AI VIDEO CLIPPING & EDITING | pending |
| 25 | Automatic Hook Generation | AI VIDEO CLIPPING & EDITING | pending |
| 26 | Video Transition Effects | AI VIDEO CLIPPING & EDITING | implemented |
| 27 | Custom Text Overlays | AI VIDEO CLIPPING & EDITING | implemented |
| 28 | Custom Media Asset Uploads | AI VIDEO CLIPPING & EDITING | implemented |
| 29 | Background Music Integration | AI VIDEO CLIPPING & EDITING | implemented |
| 30 | AI B-Roll Generation | AI VIDEO CLIPPING & EDITING | blocked |
| 31 | Stock B-Roll Integration | AI VIDEO CLIPPING & EDITING | blocked |
| 32 | AI Video B-Roll | AI VIDEO CLIPPING & EDITING | blocked |
| 33 | AI Video Upscaling | AI VIDEO CLIPPING & EDITING | blocked |
| 34 | AI Producer | AI VIDEO CLIPPING & EDITING | pending |
| 35 | Natural-Language Video Editing | AI VIDEO CLIPPING & EDITING | pending |
| 36 | Automatic Video Reframing | AI REFRAMING & VIDEO LAYOUT | pending |
| 37 | Vertical Video Conversion (9:16) | AI REFRAMING & VIDEO LAYOUT | implemented |
| 38 | Square Video Conversion (1:1) | AI REFRAMING & VIDEO LAYOUT | implemented |
| 39 | Horizontal Video Conversion (16:9) | AI REFRAMING & VIDEO LAYOUT | implemented |
| 40 | AI Subject Tracking | AI REFRAMING & VIDEO LAYOUT | pending |
| 41 | Moving Object Tracking | AI REFRAMING & VIDEO LAYOUT | pending |
| 42 | Manual Tracking Control | AI REFRAMING & VIDEO LAYOUT | pending |
| 43 | Dynamic Layout Switching | AI REFRAMING & VIDEO LAYOUT | pending |
| 44 | Speaker-Focused Framing | AI REFRAMING & VIDEO LAYOUT | pending |
| 45 | Gaming Layout Support | AI REFRAMING & VIDEO LAYOUT | pending |
| 46 | Genre-Specific Reframing | AI REFRAMING & VIDEO LAYOUT | pending |
| 47 | Custom Video Cropping | AI REFRAMING & VIDEO LAYOUT | pending |
| 48 | Automatic Caption Generation | AI CAPTIONS & SUBTITLES | blocked |
| 49 | Multilingual Speech Transcription | AI CAPTIONS & SUBTITLES | blocked |
| 50 | Animated Captions | AI CAPTIONS & SUBTITLES | pending |
| 51 | Caption Style Templates | AI CAPTIONS & SUBTITLES | implemented |
| 52 | Custom Caption Fonts | AI CAPTIONS & SUBTITLES | implemented |
| 53 | Keyword Highlighting in Captions | AI CAPTIONS & SUBTITLES | pending |
| 54 | Automatic Emoji Highlights | AI CAPTIONS & SUBTITLES | pending |
| 55 | Caption Timing Synchronization | AI CAPTIONS & SUBTITLES | implemented |
| 56 | Caption Text Editing | AI CAPTIONS & SUBTITLES | implemented |
| 57 | Automatic Profanity Censoring | AI CAPTIONS & SUBTITLES | pending |
| 58 | Custom Censored-Word Lists | AI CAPTIONS & SUBTITLES | pending |
| 59 | Brand-Specific Caption Styling | AI CAPTIONS & SUBTITLES | implemented |
| 60 | AI Speech Enhancement | AI AUDIO PROCESSING | pending |
| 61 | Background Noise Reduction | AI AUDIO PROCESSING | implemented |
| 62 | Automatic Silence Removal | AI AUDIO PROCESSING | implemented |
| 63 | Automatic Filler Word Removal | AI AUDIO PROCESSING | pending |
| 64 | Bad-Take Removal | AI AUDIO PROCESSING | pending |
| 65 | AI Voice-Over Generation | AI AUDIO PROCESSING | blocked |
| 66 | Multilingual AI Voice-Over | AI AUDIO PROCESSING | blocked |
| 67 | AI Video Dubbing | AI AUDIO PROCESSING | blocked |
| 68 | AI Sound Effects Generation | AI AUDIO PROCESSING | blocked |
| 69 | Custom Brand Templates | BRANDING & CUSTOMIZATION | pending |
| 70 | Custom Brand Colors | BRANDING & CUSTOMIZATION | implemented |
| 71 | Custom Logo Integration | BRANDING & CUSTOMIZATION | implemented |
| 72 | Branded Intro Cards | BRANDING & CUSTOMIZATION | pending |
| 73 | Branded Outro Cards | BRANDING & CUSTOMIZATION | pending |
| 74 | Custom Font Uploads | BRANDING & CUSTOMIZATION | implemented |
| 75 | Brand Vocabulary Customization | BRANDING & CUSTOMIZATION | pending |
| 76 | Custom Media Library | BRANDING & CUSTOMIZATION | scope-conflict |
| 77 | Project Renaming | BRANDING & CUSTOMIZATION | implemented |
| 78 | Clip Renaming | BRANDING & CUSTOMIZATION | implemented |
| 79 | YouTube Shorts Publishing | SOCIAL MEDIA PUBLISHING & AUTOMATION | blocked |
| 80 | Instagram Reels Publishing | SOCIAL MEDIA PUBLISHING & AUTOMATION | blocked |
| 81 | TikTok Publishing | SOCIAL MEDIA PUBLISHING & AUTOMATION | blocked |
| 82 | Social Media Post Scheduling | SOCIAL MEDIA PUBLISHING & AUTOMATION | blocked |
| 83 | Social Media Content Calendar | SOCIAL MEDIA PUBLISHING & AUTOMATION | blocked |
| 84 | Multiple Social Account Connections | SOCIAL MEDIA PUBLISHING & AUTOMATION | blocked |
| 85 | AI Video Title Generation | SOCIAL MEDIA PUBLISHING & AUTOMATION | pending |
| 86 | AI Video Description Generation | SOCIAL MEDIA PUBLISHING & AUTOMATION | pending |
| 87 | AI Hashtag Generation | SOCIAL MEDIA PUBLISHING & AUTOMATION | pending |
| 88 | Social Media Performance Analytics | SOCIAL MEDIA PUBLISHING & AUTOMATION | blocked |
| 89 | Clip Performance Analytics | SOCIAL MEDIA PUBLISHING & AUTOMATION | blocked |
| 90 | Automated Publishing Workflows | SOCIAL MEDIA PUBLISHING & AUTOMATION | blocked |
| 91 | Collaborative Team Workspace | TEAM COLLABORATION & PROJECT MANAGEMENT | scope-conflict |
| 92 | Multiple Team Member Seats | TEAM COLLABORATION & PROJECT MANAGEMENT | scope-conflict |
| 93 | Shared Video Projects | TEAM COLLABORATION & PROJECT MANAGEMENT | scope-conflict |
| 94 | Automatic Project Saving | TEAM COLLABORATION & PROJECT MANAGEMENT | scope-conflict |
| 95 | Project and Clip Collections | TEAM COLLABORATION & PROJECT MANAGEMENT | scope-conflict |
| 96 | Shareable Project Links | TEAM COLLABORATION & PROJECT MANAGEMENT | scope-conflict |
| 97 | Cloud Media Storage | TEAM COLLABORATION & PROJECT MANAGEMENT | scope-conflict |
| 98 | Sub-Team Management | TEAM COLLABORATION & PROJECT MANAGEMENT | scope-conflict |
| 99 | Team Member Permissions | TEAM COLLABORATION & PROJECT MANAGEMENT | scope-conflict |
| 100 | Priority Video Processing | TEAM COLLABORATION & PROJECT MANAGEMENT | scope-conflict |
| 101 | Video Editing API | DEVELOPER API & INTEGRATIONS | implemented |
| 102 | AI Video Clipping API | DEVELOPER API & INTEGRATIONS | blocked |
| 103 | Social Media Scheduler API | DEVELOPER API & INTEGRATIONS | blocked |
| 104 | MCP Integration | DEVELOPER API & INTEGRATIONS | pending |
| 105 | AI Agent Integration | DEVELOPER API & INTEGRATIONS | pending |
| 106 | Video Transcript Retrieval | DEVELOPER API & INTEGRATIONS | blocked |
| 107 | Clip Metadata Retrieval | DEVELOPER API & INTEGRATIONS | implemented |
| 108 | Programmatic Video Editing | DEVELOPER API & INTEGRATIONS | implemented |
| 109 | Programmatic Video Export | DEVELOPER API & INTEGRATIONS | implemented |
| 110 | Zapier Integration | DEVELOPER API & INTEGRATIONS | pending |
| 111 | Content Management System Integration | DEVELOPER API & INTEGRATIONS | pending |
| 112 | Adobe Premiere Pro Export | DEVELOPER API & INTEGRATIONS | pending |
| 113 | DaVinci Resolve Export | DEVELOPER API & INTEGRATIONS | pending |
| 114 | Local Video File Upload | VIDEO IMPORT & EXPORT | implemented |
| 115 | YouTube Video Import | VIDEO IMPORT & EXPORT | blocked |
| 116 | Google Drive Video Import | VIDEO IMPORT & EXPORT | scope-conflict |
| 117 | Vimeo Video Import | VIDEO IMPORT & EXPORT | pending |
| 118 | Twitch Video Import | VIDEO IMPORT & EXPORT | pending |
| 119 | Zoom Recording Import | VIDEO IMPORT & EXPORT | pending |
| 120 | Facebook Video Import | VIDEO IMPORT & EXPORT | pending |
| 121 | LinkedIn Video Import | VIDEO IMPORT & EXPORT | pending |
| 122 | Loom Video Import | VIDEO IMPORT & EXPORT | pending |
| 123 | Riverside Video Import | VIDEO IMPORT & EXPORT | pending |
| 124 | StreamYard Video Import | VIDEO IMPORT & EXPORT | pending |
| 125 | Rumble Video Import | VIDEO IMPORT & EXPORT | pending |
| 126 | Video Download | VIDEO IMPORT & EXPORT | implemented |
| 127 | Bulk Video Clip Export | VIDEO IMPORT & EXPORT | implemented |
| 128 | Full HD Video Rendering (1080p) | VIDEO IMPORT & EXPORT | implemented |
| 129 | Ultra HD Video Export (4K) | VIDEO IMPORT & EXPORT | pending |

## Scope conflicts are retained

Features 76 and 91–100 originally describe permanent libraries, teams, sharing, saving, storage or service tiers. Later instructions specify one owner, no Drive/video saving options, and retained URL history only. The registry preserves both facts rather than claiming these features are delivered or quietly adding them against the latest request. Feature 116 likewise records that Google Drive import was originally listed and subsequently removed.

## Phase gates

1. Private interface, real ingestion, temporary media lifecycle, timeline/manual editing, actual MP4 render and download.
2. Real local-model transcription, captions, transcript edits and evaluated highlight discovery.
3. Remaining advanced editing, multimodal/generation and external integration work, with each dependency verified before completion.

A passing phase does not imply that all 129 items are done. The final report must distinguish working features, unverified integrations, unavailable models, scope conflicts and deployment status.
