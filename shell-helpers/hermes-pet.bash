# Hermes Pets shell helpers.
#
# Usage:
#   source /home/tony/projects/hermes-pet/shell-helpers/hermes-pet.bash
#
# These helpers only call hermes-pet. They do not start shells, delete state,
# or retry work unless you explicitly run hp retry yourself.

alias hp='hermes-pet'
alias hpl='hermes-pet launch'
alias hps='hermes-pet overlay-status'
alias hpjobs='hermes-pet jobs'
alias hpfail='hermes-pet jobs --failed --last'

hpq() {
  # Default: important-only quiet mode. Pass --silent or --off as needed.
  hermes-pet quiet "$@"
}

hpmute() {
  # Default mute is 30 minutes. Pass 2h, 45m, etc. to override.
  if [ "$#" -eq 0 ]; then
    hermes-pet mute 30m
  else
    hermes-pet mute "$@"
  fi
}

hpwrap() {
  # Usage: hpwrap "Job name" -- command arg...
  if [ "$#" -lt 3 ] || [ "$2" != "--" ]; then
    printf '%s\n' 'Usage: hpwrap "Job name" -- command arg...' >&2
    return 2
  fi

  local hp_name
  hp_name=$1
  shift 2
  hermes-pet wrap --name "$hp_name" -- "$@"
}

hpbrief() {
  # Default recap window is 24h. Pass any brief options, such as --since 2h.
  hermes-pet brief "$@"
}
