"use client";
/* UI language: BG / EN, kept in the `lang` cookie (shared with the API, which
   uses it for error messages, AI output language and PDF labels). */
import { createContext, useContext } from "react";

export type Lang = "bg" | "en";

export const dict = {
  bg: {
    app_name: "Bizzmind",
    sign_in: "Вход", sign_out: "Изход", register: "Създай акаунт",
    email: "Имейл", password: "Парола", name_optional: "Име (по желание)",
    login_sub: "Влез в акаунта си, за да отвориш проектите",
    register_sub: "Създай акаунт — първият вход прави твоята организация",
    to_register: "Нямаш акаунт? Регистрирай се", to_login: "Имаш акаунт? Влез",
    login_failed: "Входът неуспешен", password_short: "Паролата трябва да е поне 8 символа.",
    projects: "Проекти", all_projects: "Всички проекти", new_project: "Нов проект",
    project_name_ph: "Име на проекта…", create: "Създай", cancel: "Отказ",
    created: "създаден", tables: "таблици", charts: "графики", knowledge: "знание",
    delete_project: "Изтрий проекта", delete: "Изтрий", project_deleted: "Проектът е изтрит.",
    delete_file: "Изтрий файла", confirm_delete_file: "Да изтрия ли „{name}“ и {n} таблици от него?", file_deleted: "Файлът е изтрит.",
    upload_done: "Готово — заредени са {n} таблици.", creating_project: "Създавам проекта…", confirm_delete_project: "Да изтрия ли проекта „{name}“ с всичките му данни?",
    no_projects_title: "Още няма проекти", no_projects_text: "Създай първия си проект и качи екселите — AI-ят ще ги проучи и ще построи дашборд.",
    tab_dash: "Дашборд", tab_files: "Файлове и знание", tab_data: "Данни",
    loading_project: "Зареждам проекта…", dash_empty_title: "Дашбордът започва тук",
    dash_empty_text: "Качи файлове — AI-ят ще ги проучи, ще ти зададе въпроси и ще построи живо табло с филтри по твоите отговори.",
    step_upload: "Качи екселите", step_interview: "Отговори на въпросите на AI", step_dashboard: "Получи жив дашборд",
    start_upload: "Качи първите файлове", clear: "Изчисти", filters: "Филтри",
    chart_error: "Тази графика не можа да се зареди с избраните филтри.",
    presentation: "Презентация", chat: "Разговор", send: "Изпрати", chat_ph: "Попитай за данните или поискай графика…",
    thinking: "Работя по задачата", done: "Готово", problem: "Възникна проблем: {msg}",
    files_title: "Файлове на проекта", files_hint: "Excel / CSV — всеки лист става таблица в базата.",
    drop_files: "Пусни Excel / CSV файлове или кликни за избор", uploading: "Качвам…",
    brand_title: "Бранд на проекта", notes_title: "Знание на проекта", note_ph: "Добави ново знание за данните…", add: "Добави",
    tables_title: "Таблици", pick_table: "Избери таблица отляво.", search_table: "Търси в таблицата…",
    rows: "реда", cols: "колони", of: "от", view: "изглед",
    edit_hint: "Кликни клетка, за да я редактираш — Enter записва, Esc отказва; промяната се отразява в графиките. Изгледите не се редактират.",
    g_sub: "AI-ят написва структурата и текста от дашборда; графиките влизат като картинки. Избери как да изглежда.",
    g_brief: "AI бриф", g_rewrite: "Пренапиши",
    brief_missing: "AI брифът не е наличен — ще използвам заглавията и изводите от дашборда. Можеш да напишеш насоки ръчно.",
    audience: "Аудитория", tone_label: "Тон", emphasis: "Акценти",
    g_theme: "Тема", g_theme_ph: "търси по цвят или тон — напр. navy, corporate…",
    theme_none: "Без избор — стандартната тема. Подредени по близост до бранда.", theme_custom_tag: "СВОЯ",
    g_text: "Текст", g_images: "Картинки", g_cards: "Слайдове", g_cards_ph: "авто", g_dims: "Пропорции", g_format: "Файл", g_lang: "Език",
    g_extra: "Насоки за презентацията", g_extra_ph: "AI-ят ги попълва сам от проекта; редактирай, ако искаш друго",
    g_extra_hint: "Попълнени автоматично от целта на анализа, бранд бука и графиките.",
    writing_deck: "Пиша презентацията", rendering_sending: "Рендирам графиките и стартирам генерирането…",
    gamma_building: "Строим презентацията… {s}с (обикновено 1–3 мин)",
    gamma_timeout: "Генерирането отне твърде дълго — опитай отново.", gamma_error: "Генерирането върна грешка.",
    done_in: "Готово за {s}с.", open_in_gamma: "Отвори презентацията", editable: "(редактируема онлайн)", download_fmt: "Свали {fmt}",
    credits_line: "Тази презентация: {used} кредита", credits_left: "Оставащи кредити: {n}",
    pres_no_credits: "Кредитите за презентации са изчерпани — свържи се с нас за още.",
    generate: "Генерирай", generating: "Генерирам…", generate_again: "Генерирай отново",
    generation_failed: "Генерирането се провали: {msg}",
    gamma_not_configured: "Генерирането на презентации не е активирано.",
    lang_bg: "BG", lang_en: "EN",
  },
  en: {
    app_name: "Bizzmind",
    sign_in: "Sign in", sign_out: "Log out", register: "Create account",
    email: "Email", password: "Password", name_optional: "Name (optional)",
    login_sub: "Sign in to your account to open your projects",
    register_sub: "Create an account — your first sign-in creates your organisation",
    to_register: "No account? Register", to_login: "Have an account? Sign in",
    login_failed: "Sign-in failed", password_short: "The password must be at least 8 characters.",
    projects: "Projects", all_projects: "All projects", new_project: "New project",
    project_name_ph: "Project name…", create: "Create", cancel: "Cancel",
    created: "created", tables: "tables", charts: "charts", knowledge: "notes",
    delete_project: "Delete project", delete: "Delete", project_deleted: "Project deleted.",
    delete_file: "Delete file", confirm_delete_file: "Delete \"{name}\" and its {n} tables?", file_deleted: "File deleted.",
    upload_done: "Done — {n} tables loaded.", creating_project: "Creating your project…", confirm_delete_project: "Delete project \"{name}\" with all its data?",
    no_projects_title: "No projects yet", no_projects_text: "Create your first project and upload your spreadsheets — the AI will explore them and build a dashboard.",
    tab_dash: "Dashboard", tab_files: "Files & knowledge", tab_data: "Data",
    loading_project: "Loading the project…", dash_empty_title: "Your dashboard starts here",
    dash_empty_text: "Upload files — the AI explores them, asks you a few questions and builds a live dashboard with filters from your answers.",
    step_upload: "Upload your spreadsheets", step_interview: "Answer the AI's questions", step_dashboard: "Get a live dashboard",
    start_upload: "Upload your first files", clear: "Clear", filters: "Filters",
    chart_error: "This chart could not load with the selected filters.",
    presentation: "Presentation", chat: "Conversation", send: "Send", chat_ph: "Ask about the data or request a chart…",
    thinking: "Working on it", done: "Done", problem: "Something went wrong: {msg}",
    files_title: "Project files", files_hint: "Excel / CSV — every sheet becomes a table in the database.",
    drop_files: "Drop Excel / CSV files or click to choose", uploading: "Uploading…",
    brand_title: "Project brand", notes_title: "Project knowledge", note_ph: "Add new knowledge about the data…", add: "Add",
    tables_title: "Tables", pick_table: "Pick a table on the left.", search_table: "Search this table…",
    rows: "rows", cols: "columns", of: "of", view: "view",
    edit_hint: "Click a cell to edit it — Enter saves, Esc cancels; charts update accordingly. Views are read-only.",
    g_sub: "The AI writes the structure and copy from the dashboard; charts are included as images. Choose how it should look.",
    g_brief: "AI brief", g_rewrite: "Rewrite",
    brief_missing: "The AI brief is unavailable — the dashboard titles and insights will be used. You can write instructions manually.",
    audience: "Audience", tone_label: "Tone", emphasis: "Emphasis",
    g_theme: "Theme", g_theme_ph: "search by colour or tone — e.g. navy, corporate…",
    theme_none: "No selection — the default theme. Sorted by closeness to the brand.", theme_custom_tag: "CUSTOM",
    g_text: "Text", g_images: "Images", g_cards: "Slides", g_cards_ph: "auto", g_dims: "Aspect", g_format: "File", g_lang: "Language",
    g_extra: "Presentation instructions", g_extra_ph: "The AI fills these in from the project; edit if you want something else",
    g_extra_hint: "Filled in automatically from the analysis goal, the brand book and the charts.",
    writing_deck: "Writing the presentation", rendering_sending: "Rendering charts and starting the generation…",
    gamma_building: "Building the presentation… {s}s (usually 1–3 min)",
    gamma_timeout: "The generation took too long — try again.", gamma_error: "The generation returned an error.",
    done_in: "Done in {s}s.", open_in_gamma: "Open the presentation", editable: "(editable online)", download_fmt: "Download {fmt}",
    credits_line: "This presentation: {used} credits", credits_left: "Credits remaining: {n}",
    pres_no_credits: "Your presentation credits are used up — contact us to top up.",
    generate: "Generate", generating: "Generating…", generate_again: "Generate again",
    generation_failed: "Generation failed: {msg}",
    gamma_not_configured: "Presentation generation is not enabled.",
    lang_bg: "BG", lang_en: "EN",
  },
} as const;

export type Key = keyof typeof dict.bg;

export function readLang(): Lang {
  if (typeof document === "undefined") return "bg";
  const m = document.cookie.match(/(?:^|;\s*)lang=(bg|en)\b/);
  if (m) return m[1] as Lang;
  return navigator.language?.toLowerCase().startsWith("bg") ? "bg" : "en";
}

export function writeLang(lang: Lang) {
  document.cookie = `lang=${lang};path=/;max-age=31536000;SameSite=Lax`;
}

export function translate(lang: Lang, key: Key, vars?: Record<string, string | number>): string {
  let s: string = dict[lang][key] ?? dict.bg[key] ?? key;
  if (vars) s = s.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? ""));
  return s;
}

export const LangContext = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({ lang: "bg", setLang: () => {} });

export function useLang() {
  return useContext(LangContext);
}

export function useT() {
  const { lang } = useContext(LangContext);
  return (key: Key, vars?: Record<string, string | number>) => translate(lang, key, vars);
}

export const localeOf = (lang: Lang) => (lang === "bg" ? "bg-BG" : "en-GB");
