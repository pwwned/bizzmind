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
    delete_project: "Изтрий проекта", confirm_delete_project: "Да изтрия ли проекта „{name}“ с всичките му данни?",
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
    delete_project: "Delete project", confirm_delete_project: "Delete project \"{name}\" with all its data?",
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
