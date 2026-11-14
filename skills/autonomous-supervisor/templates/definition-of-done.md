# Definition of Done (the same for every task; acceptance criteria say *what*, this says *finished*)

Tailor this list to the project once, record it (`$SUP decide "Definition of Done: ..." --why "standing bar"`),
then reuse it unchanged. A bar renegotiated per task is not a bar.

## Every task
- [ ] Its acceptance criteria are met, each by a check the tool ran (`$SUP criterion verify AC# --run "<command>"`)
- [ ] New behaviour has a test that fails without the change and passes with it
- [ ] The existing suite still passes
- [ ] Error paths and edge cases are handled, not only the happy path
- [ ] The change stays inside the task's files; no unrelated clean-up
- [ ] `$SUP guard` is clean: no skipped or deleted test, removed assertion, silenced checker or stub

## Every mini-goal
- [ ] It works with the rest of the system, shown by running it, not only by unit tests
- [ ] Public behaviour is documented where a user would look
- [ ] `$SUP gate --milestone M#` passes

## The project
- [ ] `$SUP gate --recheck` prints VERIFIED COMPLETE
- [ ] Assumptions the owner never confirmed are listed in the delivery

_Structure after the Definition of Done in addyosmani/agent-skills (MIT)._
