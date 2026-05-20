# Report: Forking and Pull Requests

## 1. Original Repository
* **URL:** https://codeberg.org/dnkl/foot
* **Content:** Source code of `foot` — a fast and minimalist terminal emulator for Wayland, written in C.

## 2. What is a Fork?
A fork is a personal copy of someone else's repository created under your own Codeberg account. It allows you to freely modify the code without affecting the original project.

## 3. Remote Configuration
Difference between `origin` and `upstream`:
* `origin` — Points to your personal fork on Codeberg where you can push your changes.
* `upstream` — Points to the original author's repository where you can only fetch updates.

## 4. Why sync a fork with upstream regularly?
To fetch the latest updates, bug fixes, and changes from the original author. This keeps your project up to date and prevents merge conflicts when you write your own code.

## 6. Pull Request (PR) Details
* **Problem/Improvement:** Fixed minor formatting typos and added custom notes in the README.md file.
* **Source branch:** `Tanatos/foot` -> `feature-improve-docs`
* **Target branch:** `dnkl/foot` -> `master`

## 7. What is Code Review?
Code review is a process where team members examine each other's code before merging it. It helps catch bugs early, share knowledge, and maintain high code quality.

## 3. Remote Configuration
The output of `git remote -v` after adding the upstream:
```text
origin  [https://codeberg.org/Tanatos/foot.git](https://codeberg.org/Tanatos/foot.git) (fetch)
origin  [https://codeberg.org/Tanatos/foot.git](https://codeberg.org/Tanatos/foot.git) (push)
upstream        [https://codeberg.org/dnkl/foot.git](https://codeberg.org/dnkl/foot.git) (fetch)
upstream        [https://codeberg.org/dnkl/foot.git](https://codeberg.org/dnkl/foot.git) (push)