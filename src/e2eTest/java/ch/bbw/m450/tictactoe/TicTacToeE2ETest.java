package ch.bbw.m450.tictactoe;

import static org.assertj.core.api.Assertions.assertThat;

import ch.bbw.m450.tictactoe.TicTacToePlayer.Stone;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junitpioneer.jupiter.StdIo;
import org.junitpioneer.jupiter.StdOut;

@Tag("e2e")
class TicTacToeE2ETest {

	@Test
	@Timeout(value = 5, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
	@StdIo({"abc", "0", "1", "3"})
	void invalidTextIsRejectedAndPlayerCanFinishGame(StdOut out) {
		TicTacToeMain.main(new String[0]);

		assertThat(out.capturedString()).contains("Invalid input");
		assertThat(out.capturedString()).contains("...and the winner is: CIRCLE");
	}

	@Test
	@Timeout(value = 5, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
	@StdIo({"99", "0", "0", "1", "3"})
	void outOfRangeAndOccupiedFieldsAreRejectedBeforeFinishing(StdOut out) {
		TicTacToeMain.main(new String[0]);

		assertThat(out.capturedLines())
				.filteredOn(line -> line.contains("Choose a free field from 0 to 8"))
				.hasSize(2);
		assertThat(out.capturedString()).contains("...and the winner is: CIRCLE");
	}

	@Test
	@Timeout(value = 5, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
	@StdIo({"0", "3", "6"})
	void computerBlocksTheWinningFieldOfCross(StdOut out) {
		TicTacToeMain.main(new String[0]);

		// 0-3-6 would win, but the perfect player already occupies field 6.
		assertThat(out.capturedLines())
				.filteredOn(line -> line.contains("Choose a free field from 0 to 8"))
				.hasSize(1);
		assertThat(out.capturedString()).doesNotContain("...and the winner is:");
	}

	@Test
	@Timeout(value = 5, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
	@StdIo({"0", "1", "3"})
	void circleWinsCompleteConsoleGame(StdOut out) {
		TicTacToeMain.main(new String[0]);

		assertThat(out.capturedLines())
				.filteredOn(line -> line.contains("where to put the next CROSS"))
				.hasSize(3);
		assertThat(out.capturedString()).contains("...and the winner is: CIRCLE");
	}

	@Test
	@Timeout(value = 5, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
	@StdIo({"0", "1", "6", "5", "8"})
	void drawCompletesConsoleGame(StdOut out) {
		TicTacToeMain.main(new String[0]);

		assertThat(out.capturedLines())
				.filteredOn(line -> line.contains("where to put the next CROSS"))
				.hasSize(5);
		// Like a win, a draw shows the complete final board.
		var finalBoard = new Stone[] {
				Stone.CROSS, Stone.CROSS, Stone.CIRCLE,
				Stone.CIRCLE, Stone.CIRCLE, Stone.CROSS,
				Stone.CROSS, Stone.CIRCLE, Stone.CROSS };
		assertThat(out.capturedString()).contains(TicTacToeMain.toString(finalBoard) + "it's a draw!");
	}

	@Test
	@Timeout(value = 5, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
	@StdIo({"\033[31m", "-1", "999999999999999999999999999999", "0", "1", "3"})
	void hostileControlCharactersAndHugeNumbersCannotInterruptGame(StdOut out) {
		TicTacToeMain.main(new String[0]);

		assertThat(out.capturedLines())
				.filteredOn(line -> line.contains("Invalid input.") || line.contains("Choose a free field"))
				.hasSize(3);
		assertThat(out.capturedString()).contains("...and the winner is: CIRCLE");
	}

	@Test
	@Timeout(value = 5, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
	@StdIo({"abc", "", " "})
	void repeatedInvalidInputFollowedByEofStopsWithoutHanging(StdOut out) {
		TicTacToeMain.main(new String[0]);

		assertThat(out.capturedLines())
				.filteredOn(line -> line.contains("Invalid input."))
				.hasSize(3);
		assertThat(out.capturedString()).contains("Input ended. Game stopped.");
	}

	@Test
	@Timeout(value = 5, threadMode = Timeout.ThreadMode.SEPARATE_THREAD)
	@StdIo({})
	void emptyInputStopsWithoutHanging(StdOut out) {
		TicTacToeMain.main(new String[0]);

		assertThat(out.capturedString()).contains("Input ended. Game stopped.");
	}
}
