export type Frequency = 'minutes' | 'hours' | 'daily' | 'weekly' | 'custom';
export interface ScheduleForm {
  frequency: Frequency;
  hours: string;
  minutes: string;
  at: string;
  day: string;
  custom: string;
}
export const days = [
  { value: '1', label: 'Lundi' },
  { value: '2', label: 'Mardi' },
  { value: '3', label: 'Mercredi' },
  { value: '4', label: 'Jeudi' },
  { value: '5', label: 'Vendredi' },
  { value: '6', label: 'Samedi' },
  { value: '0', label: 'Dimanche' },
];
export function fromCron(cron: string): ScheduleForm {
  const form: ScheduleForm = {
    frequency: 'custom',
    hours: '6',
    minutes: '20',
    at: '04:00',
    day: '1',
    custom: cron,
  };
  const [minute, hour, date, month, day] = cron.split(/\s+/);
  if (!minute || !hour || !day) return form;
  if (date !== '*' || month !== '*') return form;
  if (
    hour === '*' &&
    day === '*' &&
    (/^\*\/(1|2|3|4|5|6|10|12|15|20|30)$/.test(minute) || minute === '*')
  ) {
    return { ...form, frequency: 'minutes', minutes: minute === '*' ? '1' : minute.slice(2) };
  }
  if (minute === '0' && day === '*' && /^\*\/(1|2|3|4|6|8|12)$/.test(hour)) {
    return { ...form, frequency: 'hours', hours: hour.slice(2) };
  }
  if (/^\d+$/.test(minute) && /^\d+$/.test(hour) && (day === '*' || /^[0-6]$/.test(day))) {
    return {
      ...form,
      frequency: day === '*' ? 'daily' : 'weekly',
      day: day === '*' ? '1' : day,
      at: `${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`,
    };
  }
  return form;
}
export function toCron(form: ScheduleForm): string {
  if (form.frequency === 'custom') return form.custom.trim();
  if (form.frequency === 'minutes')
    return form.minutes === '1' ? '* * * * *' : `*/${form.minutes} * * * *`;
  if (form.frequency === 'hours') return `0 */${form.hours} * * *`;
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(form.at)) return '';
  const [hour, minute] = form.at.split(':').map(Number);
  return `${minute} ${hour} * * ${form.frequency === 'weekly' ? form.day : '*'}`;
}
export function scheduleLabel(cron: string) {
  const form = fromCron(cron);
  if (form.frequency === 'minutes')
    return form.minutes === '1' ? 'Chaque minute' : `Toutes les ${form.minutes} min`;
  if (form.frequency === 'hours') return `Toutes les ${form.hours} h`;
  if (form.frequency === 'daily') return `Chaque jour à ${form.at}`;
  if (form.frequency === 'weekly')
    return `${days.find((d) => d.value === form.day)?.label} à ${form.at}`;
  return `Cron personnalisé · ${cron}`;
}
