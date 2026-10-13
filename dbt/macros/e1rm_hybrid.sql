{#
  Estimated one-rep max, matching kiloplan.analytics.e1rm.e1rm_from_rpe:
  theoretical reps = reps + (10 - RPE); Brzycki up to 10 theoretical reps, Epley above.
#}
{% macro e1rm_hybrid(load, reps, rpe) %}
    case
        when ({{ reps }} + (10 - {{ rpe }})) <= 10
            then {{ load }} * 36.0 / (37 - ({{ reps }} + (10 - {{ rpe }})))
        else {{ load }} * (1 + ({{ reps }} + (10 - {{ rpe }})) / 30.0)
    end
{% endmacro %}
