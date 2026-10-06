import { redirect } from "next/navigation";

/** «Входящие» слились с «Работа → Письма»: там те же переписки плюс
 * разбор ответов ИИ и черновик ответа от Henry. */
export default function InboxMoved() {
  redirect("/app/work/letters");
}
