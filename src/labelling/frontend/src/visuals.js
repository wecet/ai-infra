import { color } from "./api";
export const classColor = (project, id) => project.classes.find((item) => item.id === id)?.color || color(id);

