# Folder 

## Set-up `uv`
Skip this step when you donethis already.
- install `uv` on your laptop `curl -LsSf https://astral.sh/uv/install.sh | sh`
- navigate to Gitea [Account Settings > Applications](https://git.openiiot.systems/user/settings/applications) and generate an access token with permissions `Package > Read and Write`
- open your profile file `~/.profile` and add the following lines to the end of the file replacing `[username]` and `[token]`
  ```
  # gitea credentials for reading/publishing packages to gitea python registry
  GITEA_USER=[username]
  GITEA_TOKEN=[token]
  
  export UV_PUBLISH_USERNAME=$GITEA_USER
  export UV_PUBLISH_PASSWORD=$GITEA_TOKEN
  export UV_INDEX_OPENIIOT_USERNAME=$GITEA_USER
  export UV_INDEX_OPENIIOT_PASSWORD=$GITEA_TOKEN
  ```
- log out and log in again (or just restart your laptop) and ensure that these variables are available in every shell session

## Project Set-Up
1. Go to the OpenIIoT Organization in Gitea.
2. Create a new repo:
   1. Under "template" > Select the template
   2. select check boxes:
      1. Git Content
      2. Branch Protection
   3. Click on "Create Repository"
3. Clone the repo to your local machine.
4. Search the project for all the "FIXME" items, and adjust them to suit your project.
5. run uv:
  1. normally, we would first run `uv init`, how ever, as we created the uv files from this template, we skip this.
  2. run `uv sync`, ths creates the .venv virtual environment.
  3. activate the virtual environment
6. Optional: Add additional packages:
  1. add any additional packages by adding them to the pyproject.toml file, or using `uv add [package]` (for dev dependencies run `uv add --dev [package]`)

## Publishing a Pre-release version
1. Ensure the you can build your project using uv from scratch:
   1. Ensure your toml file is fully up-to-date.
   2. Run `uv build` in the root of your project.
   3. Ensure that the build is successful, and that the output is as expected.
   4. Commit your latest version to your current branch.
2. Go to Gite -> Your repo -> Actions, and select the `publish` workflow.
3. Click on "Run workflow" and select the bump type:
   1. select your branch
   2. `hash` - for development releases
4. You will find your published package under at Organization level, `gitea/OpenIIoT/<PackageName>`, not under your repo.

## Publishing a Release version
1. Repeat the steps for publishing a pre-release version.
2. Ensure your code is FULLY tested, and READY FOR PRODUCTION!
3. Commit the source to `main`.
4. Click on "Run workflow" and select the bump type:
   1. select your `main` branch
   2. `major` - for a major release, breaking changes. vX.0.0
   3. `minor` - for a minor release, backward-compatible changes. vX.Y.0
   4. `patch` - for a patch release, bug fixes. vX.Y.Z
5. You will find your published package under `gitea/OpenIIoT/<PackageName>`.

## Naming convention
### Naming for Python
The used naming convetion for Python is PEP8. For more information, please visit the [PEP8 documentation](https://peps.python.org/pep-0008/).
The only exception, is a max line length of 500 characters.

## Folder structure
```js
- /
  - _TEMPLATE_README.MD         // This File, containing the template instructions. (TO BE DELETED)
  - README.md                   // containing the general information for the entire repo.
  - LICENSE                     // containing the license for the entire repo.
  - .gitignore                  // containing the git ignore file for the entire repo.
  - pyproject.toml              // containing the project metadata and dependencies for the entire repo.

// Repo Programming env
  - /.vscode                    // containing the vscode settings for the entire repo.
    - settings.json             // containing the vscode settings for the entire repo.
    - launch.json               // containing the debug run settings for the entire repo.

// Repo Cicd automation
  - /.github
    - publish.yaml              // containing the workflow details.

// Repo Test scripts
  - /test                       // containing test scripts that tests integration of multiple containers
    - test_script_1.py
    - test_script_2.py

// Repo General Documentation
  - /doc                        // containing documentation for the entire repo.
    - README.md
    - ProductPage.md            // Describes the product's introduction, features, uses, etc..
    - ....md
    - /images
      - image_1.png
      - image_2.png
  
// Python module
  - /src
    - /package_name
      - /src
        - main.py
        - ....py
        - /test                 // containing the test scripts for the python module.
          - /unit_test          // containing the unit test scripts for the python module.
              - test_script_1.py
              - test_script_2.py
          - /black_box_test     // containing the black box tests for the container.
              - test_script_1.py
              - test_script_2.py
    - /next_package...

// Python virtual environment
- /.venv                         // containing the virtual environment for the python project.
```

## Documentation
All documentation is written in MarkDown (MD) format.
Diagrams are created within the MD files, using the Mermaid syntax. The VsCode extention "Markdown Preview Mermaid Support" is used to render the diagrams.

# working rules
- Regular commits
  - Minimum Daily!
- Branch per feature
  - Branches are merged into Dev when feature is done
- Make sure to communicate with the team, and make sure to ask for help when needed.
- Keep your eyes open!
  - If you see a warning message, there is something wrong!
  - Check ur own work, and try to break it.
- Testing by developer
  - Test each and every change that you do!
  - You add three buttons, or create 5 new functions, test them!
- NEVER COPY CODE
  - Instead of copying code, add it to the library in /lib, and import it. This you we can reuse your code easier.

# branching
- `main` is the production branch
  - Manged by the Architect -> Robbert Brand
  - Pull requests are made to this branch, by tester
- `test` is the test branch
  - Managed by the tester -> ...
- `dev` is the development branch
  - Is the branch where all the features are merged into by developers, upon succesfull testing by the developers them selves.
- `featureXYZ` is the feature branch
  - Is the branch where the developers work on their features, make MANY commits, and merge into `dev` when tested by the developer.

****