import { Hero } from "@/sections/hero";
import { Proof } from "@/sections/proof";
import { Problem } from "@/sections/problem";
import { Solution } from "@/sections/solution";
import { Services } from "@/sections/services";
import { Platform } from "@/sections/platform";
import { Difference } from "@/sections/difference";
import { Process } from "@/sections/process";
import { Outcomes } from "@/sections/outcomes";
import { Faq } from "@/sections/faq";
import { Book } from "@/sections/book";
import { Contact } from "@/sections/contact";

/* Section order is the contract — do not reorder without updating
   SITE_CONTRACTS.md and nav anchors. */
export default function Home() {
  return (
    <>
      <Hero />
      <Proof />
      <Problem />
      <Solution />
      <Services />
      <Platform />
      <Difference />
      <Process />
      <Outcomes />
      <Faq />
      <Book />
      <Contact />
    </>
  );
}
