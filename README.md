[![Python 2.6 2.7 3.7](https://img.shields.io/badge/python-2.6%20%7C%202.7%20%7C%203.7-blue.svg)](https://www.python.org/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
![GitHub release (latest by date including pre-releases)](https://img.shields.io/github/v/release/nfa-vfxim/tk-multi-reviewsubmission2?include_prereleases)
[![GitHub issues](https://img.shields.io/github/issues/nfa-vfxim/tk-multi-reviewsubmission2)](https://github.com/nfa-vfxim/tk-multi-reviewsubmission2/issues)

# tk-multi-reviewsubmission2

Easily create and publish QuickTime preview renders (flipbooks/playblasts) from the ShotGrid menu.

Supported toolkits: `tk-houdini`, `tk-maya`

_Requires Nuke for creating slates._

|                             Houdini                              |                          Maya                           |
|:----------------------------------------------------------------:|:-------------------------------------------------------:|
| ![Houdini Dialog](resources/dialog_houdini.png "Houdini Dialog") | ![Maya Dialog](resources/dialog_maya.png "Maya Dialog") |

![Slate](resources/slate.jpg "Slate")
Slate

![Review](resources/review.jpg "Review")
Review

## Configuration

### Strings

| Key              | Description                                                |
|------------------|------------------------------------------------------------|
| `company_name`   | Specify the company name that should be on the slates      |
| `display_name`   | Specify the name that should be used in menus and the main |
| `cut_in_field`   | ShotGrid field name of cut in frame                        |
| `cut_out_field`  | ShotGrid field name of cut out frame                       |
| `fps_field`      | ShotGrid field name of fps                                 |

### Paths

| Key                 | Description                                                 |
|---------------------|-------------------------------------------------------------|
| `nuke_path_linux`   | Linux path to your Nuke installation for creating slates.   |
| `nuke_path_mac`     | Mac path to your Nuke installation for creating slates.     |
| `nuke_path_windows` | Windows path to your Nuke installation for creating slates. |
| `slate_logo`        | Relative app path to the logo displayed on the slate        |

### Templates

| Key                    | Description                            |
|------------------------|----------------------------------------|
| `work_file_template`   | Template for your current work file.   |
| `review_file_template` | Template for the exported review file. |

### Hooks

| Key                 | Description                                                   |
|---------------------|---------------------------------------------------------------|
| `helper_hook`       | Implements helper functions.                                  |
| `progress_hook`     | Implements progress bar functions.                            |
| `render_media_hook` | Implements how media get generated while this app is running. |

## License

[MIT](https://choosealicense.com/licenses/mit/)
