Message from the user, received mid-session:

> Two things I forgot to put in the brief:
> 1. Our CI scripts treat exit code 2 as "bad usage", so a **missing input file must exit with code 3**, not 2. (Bad `--max-width` stays exit 2.)
> 2. Please support an environment variable `CSVMD_MAX_WIDTH` that sets the default max width when `--max-width` isn't passed. The flag always wins over the variable.
