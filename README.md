# python-concentriq

Python package for interacting with a Proscia Concentriq instance

## Documentation

This package installs a cli tool called `concentriq`

```console
$ concentriq image --help
Usage: concentriq [OPTIONS] COMMAND [ARGS]...

Options:
  --install-completion [bash|zsh|fish|powershell|pwsh]
                                  Install completion for the specified
                                  shell.
  --show-completion [bash|zsh|fish|powershell|pwsh]
                                  Show completion for the specified
                                  shell, to copy it or customize the
                                  installation.
  --help                          Show this message and exit.

Commands:
  annotation
  config
  folder
  group
  image
  imageset

  #### Proscia Concentriq via Python ####

```

To get info for let's say an imageset:

```console
$ concentriq imageset info 196

                             Imageset #196
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Key                ┃ Value                                           ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ id                 │ 196                                             │
│ thumbnail_url      │ https://s3.eu-central-1.amazonaws.com/concentr… │
│ shared_with_public │ False                                           │
│ is_favorite        │ False                                           │
│ name               │ Some-Test-Files                                 │
│ created            │ 2021-10-25 16:23:32.080000+00:00                │
│ last_modified      │ 2021-10-25 16:23:32.080000+00:00                │
│ image_count        │ 12                                              │
│ total_size         │ 10731152500                                     │
│ owner_name         │ <owner-account>                                 │
│ owner_id           │ 58                                              │
│ description        │                                                 │
│ group_id           │ 50                                              │
│ group_name         │ PathDrive                                       │
│ status             │ None                                            │
│ assignedUser       │ None                                            │
│ metadata           │ None                                            │
│ workflow           │ None                                            │
│ stage              │ None                                            │
│ completedTimestamp │ None                                            │
│ workflowId         │ None                                            │
│ stageId            │ None                                            │
│ isStat             │ False                                           │
│ assignedUserId     │ -1                                              │
└────────────────────┴─────────────────────────────────────────────────┘
```

Groups

```console
$ concentriq group info 50
                      Group #50
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Key             ┃ Value                            ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ id              │ 50                               │
│ name            │ PathDrive                        │
│ image_set_count │ None                             │
│ owner_name      │ Andreas Poehlmann                │
│ owner_id        │ 37                               │
│ is_favorite     │ False                            │
│ description     │ None                             │
│ created         │ 2021-07-24 10:17:34.840000+00:00 │
│ last_modified   │ 2021-10-25 16:23:32.080000+00:00 │
└─────────────────┴──────────────────────────────────┘

```

To create a new imageset
```console
$ concentriq imageset create --group-id 50 "My new imageset"

[... outputs info for newly created imageset ...]

```

To upload an image

```console
$ concentriq image upload --imageset-id 196 /path/to/your/local/image.svs

[ ... will print progress for upload ...]

```

## Initial setup

`pip install .` the python package, and then run

```shell
concentriq config setup
```

You will have to provide three settings:

- `API_URL`: your proscia concentriq api url, i.e. `https://app.concentriq.my-company.com/api/`
- `user`: the user account email you want to use with the cli
- `pass`: the password of that user account


## Development Installation

Just install as an editable installation:

```
pip install -e .
```

## Acknowledgements

Build with love by Santi Villalba and Andreas Poehlmann from the _Machine Learning Research_ group at Bayer.

`python-concentriq`: copyright 2020 Bayer AG
